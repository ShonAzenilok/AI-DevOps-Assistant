"""Amazon Bedrock LLM client (Converse API).

Uses the AWS credentials the user entered during onboarding — no separate API key.
Exposes chat_stream / chat_once for the agent orchestrator and action executor.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from queue import Queue
from typing import Any

import boto3

from app.config import settings
from app.core.session import SessionStore
from app.services.mcp.helpers import parse_tool_arguments

logger = logging.getLogger(__name__)

_STREAM_DONE = object()
MAX_TOKENS = 4096


def tools_to_bedrock(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert function-tool specs to a Bedrock toolConfig."""
    specs = []
    for tool in tools:
        fn = tool.get("function") or {}
        specs.append(
            {
                "toolSpec": {
                    "name": fn.get("name", "tool"),
                    "description": fn.get("description") or fn.get("name", "tool"),
                    "inputSchema": {
                        "json": fn.get("parameters") or {"type": "object", "properties": {}}
                    },
                }
            }
        )
    return {"tools": specs}


def messages_to_bedrock(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Translate chat messages into Bedrock Converse messages + system blocks."""
    system: list[dict[str, str]] = []
    converted: list[dict[str, Any]] = []
    pending_tool_ids: list[str] = []

    def append_blocks(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"].extend(blocks)
        else:
            converted.append({"role": role, "content": blocks})

    for message in messages:
        role = message.get("role", "user")
        text = message.get("content") or ""

        if role == "system":
            if text:
                system.append({"text": text})
            continue

        if role == "tool":
            tool_use_id = pending_tool_ids.pop(0) if pending_tool_ids else str(uuid.uuid4())
            append_blocks(
                "user",
                [
                    {
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"text": text or "(no output)"}],
                        }
                    }
                ],
            )
            continue

        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            if text:
                blocks.append({"text": text})
            tool_calls = message.get("tool_calls") or []
            pending_tool_ids = []
            for call in tool_calls:
                fn = call.get("function") or {}
                arguments = parse_tool_arguments(fn.get("arguments"))
                call_id = call.get("id") or str(uuid.uuid4())
                pending_tool_ids.append(call_id)
                blocks.append(
                    {
                        "toolUse": {
                            "toolUseId": call_id,
                            "name": fn.get("name", "tool"),
                            "input": arguments or {},
                        }
                    }
                )
            append_blocks("assistant", blocks)
            continue

        if text:
            append_blocks("user", [{"text": text}])

    return converted, system


def bedrock_message_to_chat(output_message: dict[str, Any]) -> dict[str, Any]:
    """Convert a Bedrock Converse output message to the internal chat format."""
    content = ""
    tool_calls: list[dict[str, Any]] = []
    for block in output_message.get("content") or []:
        if "text" in block:
            content += block["text"]
        elif "toolUse" in block:
            tool_use = block["toolUse"]
            tool_calls.append(
                {
                    "id": tool_use.get("toolUseId") or str(uuid.uuid4()),
                    "function": {
                        "name": tool_use.get("name", ""),
                        "arguments": tool_use.get("input") or {},
                    },
                }
            )
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


class BedrockClient:
    """LLM client backed by Amazon Bedrock's Converse API."""

    def __init__(self, session_store: SessionStore) -> None:
        self._session_store = session_store
        self.model = settings.bedrock_model_id

    def _runtime_client(self) -> Any:
        credentials = self._session_store.credentials
        if credentials is None:
            raise RuntimeError("AWS credentials not set. Complete onboarding first.")
        return boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
        )

    def _base_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        converted, system = messages_to_bedrock(messages)
        kwargs: dict[str, Any] = {
            "modelId": self.model,
            "messages": converted,
            "inferenceConfig": {
                "maxTokens": MAX_TOKENS,
                "temperature": settings.llm_temperature,
            },
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = tools_to_bedrock(tools)
        return kwargs

    async def chat_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        kwargs = self._base_kwargs(messages, tools)
        client = self._runtime_client()
        response = await asyncio.to_thread(client.converse, **kwargs)
        output_message = (response.get("output") or {}).get("message") or {}
        return {"message": bedrock_message_to_chat(output_message), "done": True}

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream Converse events, yielding token deltas and a final tool_calls message."""
        kwargs = self._base_kwargs(messages, tools)
        client = self._runtime_client()
        queue: Queue[Any] = Queue()
        loop = asyncio.get_running_loop()

        def pump() -> None:
            try:
                response = client.converse_stream(**kwargs)
                for event in response["stream"]:
                    queue.put(event)
            except Exception as exc:
                queue.put(exc)
            finally:
                queue.put(_STREAM_DONE)

        # Fire-and-forget: pump signals completion via the _STREAM_DONE sentinel,
        # and errors are forwarded through the queue.
        loop.run_in_executor(None, pump)

        # Per-content-block accumulation state for tool-use input JSON.
        current_tool: dict[str, Any] | None = None
        current_tool_json = ""
        tool_calls: list[dict[str, Any]] = []

        while True:
            event = await asyncio.to_thread(queue.get)
            if event is _STREAM_DONE:
                break
            if isinstance(event, Exception):
                raise event

            if "contentBlockStart" in event:
                start = (event["contentBlockStart"].get("start") or {}).get("toolUse")
                if start:
                    current_tool = {
                        "id": start.get("toolUseId") or str(uuid.uuid4()),
                        "name": start.get("name", ""),
                    }
                    current_tool_json = ""

            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta") or {}
                if "text" in delta and delta["text"]:
                    yield {
                        "message": {"role": "assistant", "content": delta["text"]},
                        "done": False,
                    }
                elif "toolUse" in delta:
                    current_tool_json += delta["toolUse"].get("input") or ""

            elif "contentBlockStop" in event:
                if current_tool is not None:
                    arguments = parse_tool_arguments(current_tool_json or None)
                    tool_calls.append(
                        {
                            "id": current_tool["id"],
                            "function": {"name": current_tool["name"], "arguments": arguments},
                        }
                    )
                    current_tool = None
                    current_tool_json = ""

            elif "messageStop" in event:
                final: dict[str, Any] = {"role": "assistant", "content": ""}
                if tool_calls:
                    final["tool_calls"] = tool_calls
                yield {"message": final, "done": True}
