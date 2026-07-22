"""Lightweight Debugging chat: Bedrock + local read_file tool (hello-world jail)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.models.schemas import ChatHistoryItem
from app.services.bedrock.client import BedrockClient
from app.services.debug.code_reader import get_code_root, read_file_slice, search_code
from app.services.mcp.helpers import truncate_output
from app.services.mcp.tools import parse_tool_call
from app.streaming.ndjson import ndjson_line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DevBot's Debugging assistant for the hello-world app under {code_root}.
Help the user understand CloudWatch errors and the hello-world codebase.
Use the read_file tool to open files under hello-world (relative paths like server.js or src/App.tsx).
Use search_code to find symbols or error strings.
Suggest fixes in markdown; do not claim you applied changes. Stay scoped to hello-world.
"""

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file under hello-world/. Optional line centers a slice.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path, e.g. server.js"},
                "line": {"type": "integer", "description": "Optional 1-based line to center on"},
            },
            "required": ["path"],
        },
    },
}

SEARCH_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": "Search hello-world/ source for a string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
}


def _run_local_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "read_file":
        path = str(arguments.get("path") or "")
        line_raw = arguments.get("line")
        line = int(line_raw) if line_raw is not None else None
        return read_file_slice(path, line=line)
    if name == "search_code":
        query = str(arguments.get("query") or "")
        hits = search_code(query)
        if not hits:
            return "No matches."
        return "\n".join(f"{rel}:{lineno}: {text}" for rel, lineno, text in hits)
    return f"Unknown tool: {name}"


class DebugChatOrchestrator:
    def __init__(self, llm: BedrockClient) -> None:
        self.llm = llm

    async def run_turn(
        self,
        message: str,
        history: list[ChatHistoryItem],
    ) -> AsyncIterator[str]:
        try:
            async for line in self._run_turn(message, history):
                yield line
        except Exception as exc:
            logger.exception("Debug chat turn failed")
            yield ndjson_line({"type": "error", "detail": str(exc)})
        finally:
            yield ndjson_line({"type": "done"})

    async def _run_turn(
        self,
        message: str,
        history: list[ChatHistoryItem],
    ) -> AsyncIterator[str]:
        tools = [READ_FILE_TOOL, SEARCH_CODE_TOOL]
        root = get_code_root()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT.format(code_root=root)}
        ]
        for item in history:
            messages.append({"role": item.role, "content": item.text})
        messages.append({"role": "user", "content": message})

        emitted = False
        for _ in range(settings.agent_max_iterations):
            assistant_content = ""
            tool_calls: list[dict[str, Any]] = []

            async for chunk in self.llm.chat_stream(messages, tools=tools):
                msg = chunk.get("message") or {}
                content = msg.get("content") or ""
                if content:
                    assistant_content += content
                    emitted = True
                    yield ndjson_line({"type": "token", "text": content})
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]
                if chunk.get("done") and msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]

            if not tool_calls:
                if not emitted:
                    yield ndjson_line(
                        {
                            "type": "token",
                            "text": "I didn't get a response — try rephrasing.",
                        }
                    )
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": tool_calls,
                }
            )

            for raw_call in tool_calls:
                tool_name, arguments = parse_tool_call(raw_call)
                # Normalize name (models may invent prefixes)
                base = tool_name.rsplit("___", 1)[-1]
                if base in {"read_file", "search_code"}:
                    tool_name = base
                started = time.perf_counter()
                try:
                    output = _run_local_tool(tool_name, arguments)
                except Exception as exc:
                    output = str(exc)
                duration_ms = int((time.perf_counter() - started) * 1000)
                detail = (
                    str(arguments.get("path") or arguments.get("query") or "")
                    or json.dumps(arguments, default=str)[:200]
                )
                emitted = True
                yield ndjson_line(
                    {
                        "type": "tool",
                        "tool": {
                            "label": tool_name,
                            "detail": detail,
                            "durationMs": duration_ms,
                            "output": truncate_output(output) or None,
                        },
                    }
                )
                messages.append(
                    {"role": "tool", "content": output or "(empty)", "name": tool_name}
                )

        yield ndjson_line(
            {
                "type": "token",
                "text": "\n\nReached the maximum number of tool steps for this turn.",
            }
        )
