from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.models.schemas import ChatHistoryItem, PendingAction, StagedMcpCall
from app.services.actions.registry import ActionRegistry
from app.services.mcp.manager import McpClientManager
from app.services.mcp.tools import (
    build_action_resource,
    coerce_read_only_command,
    invoke_mcp_tool,
    is_destructive_tool_call,
    is_recoverable_tool_error,
    is_write_tool_call,
    mcp_tools_to_ollama,
    parse_tool_call,
    set_cli_command,
    tool_call_label,
)
from app.services.ollama.client import OllamaClient
from app.streaming.ndjson import ndjson_line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are DevBot, a local-first AI DevOps assistant for AWS.
The user's default AWS region is {region}. Include --region {region} in AWS CLI commands when needed.

Rules for AWS CLI commands:
- For listing or inspecting resources, use read-only commands: list-*, describe-*, get-*.
- Do NOT use run-instances, create-*, put-*, or update-* unless the user explicitly asks to create or change something.
- EC2 tags on run-instances use --tag-specifications, never --tags.
- If a command fails validation, read the error and fix the exact parameter names before retrying.

Examples:
- S3 buckets: aws s3api list-buckets
- EC2 instances: aws ec2 describe-instances --region {region}

Prefer read-only operations. Destructive or write operations are staged for user confirmation.
After tool results arrive, summarize them clearly for the user in plain language.
"""


def _summarize_tool_output(outputs: list[str]) -> str:
    joined = "\n\n".join(output for output in outputs if output.strip())
    if not joined:
        return "The AWS command completed but returned no output."
    if len(joined) > 4000:
        return joined[:4000] + "\n\n...(truncated)"
    return joined


class AgentOrchestrator:
    def __init__(
        self,
        ollama: OllamaClient,
        mcp: McpClientManager,
        actions: ActionRegistry,
    ) -> None:
        self.ollama = ollama
        self.mcp = mcp
        self.actions = actions

    async def run_turn(
        self,
        message: str,
        history: list[ChatHistoryItem],
    ) -> AsyncIterator[str]:
        try:
            async for line in self._run_turn(message, history):
                yield line
        except Exception as exc:
            logger.exception("Agent turn failed")
            yield ndjson_line({"type": "error", "detail": str(exc)})
        finally:
            yield ndjson_line({"type": "done"})

    async def _run_turn(
        self,
        message: str,
        history: list[ChatHistoryItem],
    ) -> AsyncIterator[str]:
        ollama_tools = mcp_tools_to_ollama(self.mcp.tools)
        region = self.mcp.user_region or "us-east-1"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(region=region)}
        ]
        for item in history:
            messages.append({"role": item.role, "content": item.text})
        messages.append({"role": "user", "content": message})

        tool_outputs: list[str] = []
        emitted_text = False

        for iteration in range(settings.agent_max_iterations):
            assistant_message: dict[str, Any] = {"role": "assistant", "content": ""}
            tool_calls: list[dict[str, Any]] = []

            async for chunk in self.ollama.chat_stream(messages, tools=ollama_tools or None):
                msg = chunk.get("message") or {}
                content = msg.get("content") or ""
                if content:
                    assistant_message["content"] += content
                    emitted_text = True
                    yield ndjson_line({"type": "token", "text": content})

                # qwen3.5 emits tool_calls in a pre-done chunk, not the final one.
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]

                if chunk.get("done") and msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]

            if not tool_calls:
                if not emitted_text and tool_outputs:
                    summary = _summarize_tool_output(tool_outputs)
                    emitted_text = True
                    yield ndjson_line({"type": "token", "text": summary})
                elif not emitted_text:
                    logger.warning("Model returned no content or tool calls for: %s", message[:120])
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                tool_name, arguments = parse_tool_call(tool_call)

                cli_command = arguments.get("cli_command") or arguments.get("command")
                if isinstance(cli_command, str):
                    corrected = coerce_read_only_command(message, region, cli_command)
                    corrected = self.mcp.ensure_cli_region(corrected)
                    set_cli_command(arguments, corrected)

                label, detail = tool_call_label(tool_name, arguments)

                if is_destructive_tool_call(tool_name, arguments) or is_write_tool_call(
                    tool_name, arguments
                ):
                    staged = StagedMcpCall(
                        tool_name=tool_name,
                        arguments=arguments,
                        label=label,
                        detail=detail,
                        resource=build_action_resource(arguments),
                    )
                    pending: PendingAction = self.actions.stage(staged)
                    emitted_text = True
                    yield ndjson_line({"type": "confirm", "action": pending.model_dump(mode="json")})
                    tool_output = (
                        "This write/destructive operation was staged for user confirmation. "
                        "Do not retry until the user confirms or cancels."
                    )
                else:
                    tool, output = await invoke_mcp_tool(self.mcp.session, tool_name, arguments)
                    tool_outputs.append(output)
                    emitted_text = True
                    yield ndjson_line({"type": "tool", "tool": tool.model_dump(mode="json")})
                    if is_recoverable_tool_error(output):
                        tool_output = (
                            f"{output}\n\nThe AWS CLI command was invalid. "
                            "Fix the parameter names shown above and try again with a corrected command."
                        )
                    else:
                        tool_output = output or "Tool completed successfully."

                messages.append(
                    {
                        "role": "tool",
                        "content": tool_output,
                        "name": tool_name,
                    }
                )

        if not emitted_text and tool_outputs:
            yield ndjson_line({"type": "token", "text": _summarize_tool_output(tool_outputs)})
        else:
            yield ndjson_line(
                {
                    "type": "token",
                    "text": "\n\nI reached the maximum number of tool steps for this turn. "
                    "Try a narrower request or continue in a follow-up message.",
                }
            )
