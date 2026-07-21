"""ReAct-style executor for confirmed actions.

Executes the user-approved command; when AWS rejects it (missing/invalid
parameters), feeds the exact error back to the model, gets a corrected command,
validates it locally, and retries — up to MAX_EXECUTION_ATTEMPTS total attempts.

Safety guard: a corrected command must target the same AWS service and operation
the user confirmed (e.g. `ec2 run-instances`); the loop never escalates to a
different operation without a new confirmation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.schemas import ActionResultResponse, StagedMcpCall
from app.services.aws_cli.validator import cli_validator
from app.services.mcp.helpers import parse_cli_head, truncate_output
from app.services.mcp.manager import McpClientManager
from app.services.mcp.tools import (
    get_cli_command,
    invoke_mcp_tool,
    is_tool_error_output,
    parse_tool_call,
    set_cli_command,
)
from app.services.bedrock.client import BedrockClient

logger = logging.getLogger(__name__)

MAX_EXECUTION_ATTEMPTS = 3

FIX_SYSTEM_PROMPT = """You are an AWS CLI expert. An AWS CLI command was executed and failed.
Fix the command and call the call_aws tool with the corrected command.
Rules:
- Keep the same AWS service and operation and the original intent.
- Only add or fix the parameters mentioned in the error message.
- Copy required parameter names exactly from the error message.
"""


def _operation_key(cli_command: str) -> tuple[str, str]:
    return parse_cli_head(cli_command)


def _call_aws_tool_schema(tool_name: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": "Execute an AWS CLI command.",
                "parameters": {
                    "type": "object",
                    "properties": {"cli_command": {"type": "string"}},
                    "required": ["cli_command"],
                },
            },
        }
    ]


def _extract_corrected_command(response: dict[str, Any]) -> str | None:
    message = response.get("message") or {}
    for raw_call in message.get("tool_calls") or []:
        _, arguments = parse_tool_call(raw_call)
        cli_command = get_cli_command(arguments)
        if cli_command:
            return cli_command
    # Fallback: model answered in plain text; look for an `aws ...` line.
    content = message.get("content") or ""
    for line in content.splitlines():
        stripped = line.strip().strip("`")
        if stripped.startswith("aws "):
            return stripped
    return None


async def _propose_correction(
    llm: BedrockClient,
    tool_name: str,
    failed_command: str,
    error_output: str,
) -> str | None:
    messages = [
        {"role": "system", "content": FIX_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"This command failed:\n{failed_command}\n\n"
                f"Error:\n{error_output[:3000]}\n\n"
                "Call call_aws with the corrected command."
            ),
        },
    ]
    try:
        response = await llm.chat_once(messages, tools=_call_aws_tool_schema(tool_name))
    except Exception:
        logger.exception("Correction request to Bedrock failed")
        return None
    return _extract_corrected_command(response)


async def execute_with_retry(
    call: StagedMcpCall,
    mcp: McpClientManager,
    llm: BedrockClient,
) -> ActionResultResponse:
    """Execute a confirmed action, self-correcting on AWS errors (ReAct loop)."""
    arguments = dict(call.arguments)
    approved_command = get_cli_command(arguments)

    # Non-CLI tool calls: execute once, no correction loop possible.
    if approved_command is None:
        _, output = await invoke_mcp_tool(mcp.session, call.tool_name, arguments)
        if is_tool_error_output(output):
            return ActionResultResponse(
                status="failed", summary=call.label, output=truncate_output(output)
            )
        return ActionResultResponse(
            status="executed",
            summary=f"Completed — {call.label}",
            output=truncate_output(output),
        )

    approved_op = _operation_key(approved_command)
    attempt_log: list[str] = []
    attempts_made = 0
    command = approved_command

    for attempt in range(1, MAX_EXECUTION_ATTEMPTS + 1):
        attempts_made = attempt
        set_cli_command(arguments, command)
        _, output = await invoke_mcp_tool(mcp.session, call.tool_name, arguments)

        if not is_tool_error_output(output):
            summary = f"Completed — {call.label}"
            if attempt > 1:
                summary += f" (corrected after {attempt - 1} failed attempt{'s' if attempt > 2 else ''})"
                output = f"Executed command: {command}\n\n{output}"
            return ActionResultResponse(
                status="executed", summary=summary, output=truncate_output(output)
            )

        attempt_log.append(f"Attempt {attempt}: {command}\n{output}")
        logger.warning(
            "Confirmed action failed (attempt %d/%d): %s",
            attempt,
            MAX_EXECUTION_ATTEMPTS,
            output[:300],
        )

        if attempt == MAX_EXECUTION_ATTEMPTS:
            break

        corrected = await _propose_correction(llm, call.tool_name, command, output)
        if not corrected:
            attempt_log.append("Could not generate a corrected command.")
            break

        corrected = mcp.ensure_cli_region(" ".join(corrected.split()))
        if corrected == command:
            attempt_log.append("Model repeated the same failing command; stopping.")
            break
        if _operation_key(corrected) != approved_op:
            attempt_log.append(
                f"Rejected correction (different operation than confirmed): {corrected}"
            )
            break

        validation = cli_validator.validate(corrected)
        if not validation.ok:
            attempt_log.append(f"Rejected correction (invalid: {validation.error}): {corrected}")
            break

        command = corrected

    return ActionResultResponse(
        status="failed",
        summary=f"{call.label} (after {attempts_made} attempt{'s' if attempts_made != 1 else ''})",
        output=truncate_output("\n\n".join(attempt_log)),
    )
