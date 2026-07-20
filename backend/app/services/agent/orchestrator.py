from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.models.schemas import ChatHistoryItem, PendingAction, StagedMcpCall
from app.services.actions.registry import ActionRegistry
from app.services.aws_cli.validator import cli_validator
from app.services.bedrock.client import BedrockClient
from app.services.mcp.manager import McpClientManager
from app.services.mcp.tools import (
    build_action_resource,
    build_action_summary,
    coerce_read_only_command,
    get_cli_command,
    invoke_mcp_tool,
    is_destructive_tool_call,
    is_recoverable_tool_error,
    is_write_tool_call,
    mcp_tools_to_llm,
    parse_tool_call,
    resolve_tool_name,
    set_cli_command,
)
from app.streaming.ndjson import ndjson_line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are DevBot, a local-first AI DevOps assistant for AWS.
The user's default AWS region is {region}. Include --region {region} in AWS CLI commands when needed.

Tool workflow:
- READ (list/describe/get/show): call call_aws directly with a read-only CLI command.
- WRITE/CREATE/UPDATE/DELETE: call call_aws with the CLI command. Every command is
  validated locally first; if it is invalid you will get the exact error and the list of
  valid parameters — correct the command and call call_aws again.
- If you are unsure of the CLI syntax for an operation, use the documentation search tool
  to look it up before calling call_aws.

Examples of read-only commands:
- S3 buckets: aws s3api list-buckets
- EC2 instances: aws ec2 describe-instances --region {region}

Use only parameter names that appear in AWS CLI documentation or in tool error messages.
If a command is rejected, copy the corrected parameters exactly from the error.

Write/destructive operations are staged for user confirmation in the UI (Confirm / Cancel).
Never ask the user to reply yes/no — the confirmation card is the only approval path.
After read tool results arrive, summarize them clearly for the user in plain language.
"""

MAX_VALIDATION_RETRIES = 3


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
        llm: BedrockClient,
        mcp: McpClientManager,
        actions: ActionRegistry,
    ) -> None:
        self.llm = llm
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
        llm_tools = mcp_tools_to_llm(self.mcp.tools)
        region = self.mcp.user_region or "us-east-1"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(region=region)}
        ]
        for item in history:
            messages.append({"role": item.role, "content": item.text})
        messages.append({"role": "user", "content": message})

        tool_outputs: list[str] = []
        emitted_text = False
        validation_failures = 0

        for _ in range(settings.agent_max_iterations):
            assistant_message: dict[str, Any] = {"role": "assistant", "content": ""}
            tool_calls: list[dict[str, Any]] = []

            async for chunk in self.llm.chat_stream(messages, tools=llm_tools or None):
                msg = chunk.get("message") or {}
                content = msg.get("content") or ""
                if content:
                    assistant_message["content"] += content
                    emitted_text = True
                    yield ndjson_line({"type": "token", "text": content})

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

                # Models sometimes drop server prefixes (search_documentation vs
                # aws___search_documentation) or invent tool names entirely.
                resolved = resolve_tool_name(tool_name, self.mcp.tools)
                if resolved is None:
                    available = ", ".join(t.name for t in self.mcp.tools)
                    tool_output = (
                        f"Unknown tool '{tool_name}'. Available tools: {available}. "
                        "Use call_aws to run AWS CLI commands."
                    )
                    emitted_text = True
                    yield ndjson_line(
                        {
                            "type": "tool",
                            "tool": {
                                "label": "Unknown tool",
                                "detail": tool_name,
                                "output": tool_output,
                            },
                        }
                    )
                    messages.append({"role": "tool", "content": tool_output, "name": tool_name})
                    continue
                tool_name = resolved

                cli_command = get_cli_command(arguments)
                if isinstance(cli_command, str):
                    corrected = coerce_read_only_command(message, region, cli_command)
                    corrected = self.mcp.ensure_cli_region(corrected)
                    set_cli_command(arguments, corrected)
                    cli_command = get_cli_command(arguments)

                if cli_command is not None:
                    validation = cli_validator.validate(cli_command)
                    if not validation.ok:
                        validation_failures += 1
                        params_hint = ""
                        if validation.valid_params:
                            params_hint = (
                                " Valid parameters for this operation: "
                                + ", ".join(validation.valid_params)
                                + "."
                            )
                        tool_output = (
                            f"Invalid AWS CLI: {validation.error}{params_hint} "
                            "Correct the command and call call_aws again."
                        )
                        emitted_text = True
                        yield ndjson_line(
                            {
                                "type": "tool",
                                "tool": {
                                    "label": "Invalid command",
                                    "detail": cli_command,
                                    "output": tool_output[:8000],
                                },
                            }
                        )
                        if validation_failures >= MAX_VALIDATION_RETRIES:
                            yield ndjson_line(
                                {
                                    "type": "token",
                                    "text": "\n\nI couldn't produce a valid AWS CLI command for "
                                    "this request after several attempts. Try rephrasing with "
                                    "more specifics (service, resource, and parameters).",
                                }
                            )
                            return
                        messages.append(
                            {"role": "tool", "content": tool_output, "name": tool_name}
                        )
                        continue

                if cli_command is not None and (
                    is_destructive_tool_call(tool_name, arguments)
                    or is_write_tool_call(tool_name, arguments)
                ):
                    action_label, action_summary = build_action_summary(cli_command)
                    staged = StagedMcpCall(
                        tool_name=tool_name,
                        arguments=arguments,
                        label=action_label,
                        detail=action_summary,
                        resource=build_action_resource(arguments, summary=action_summary),
                    )
                    pending: PendingAction = self.actions.stage(staged)
                    emitted_text = True
                    yield ndjson_line({"type": "confirm", "action": pending.model_dump(mode="json")})
                    # Hard stop: Confirm/Cancel on the card is the only approval path.
                    # Do not continue the loop or let the model ask yes/no in chat.
                    return

                tool, output = await invoke_mcp_tool(self.mcp.session, tool_name, arguments)
                tool_outputs.append(output)
                emitted_text = True
                yield ndjson_line({"type": "tool", "tool": tool.model_dump(mode="json")})
                if is_recoverable_tool_error(output):
                    tool_output = (
                        f"{output}\n\nThe AWS CLI command was invalid. "
                        "Correct the parameters using the error above and call call_aws again."
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
