from __future__ import annotations

import json
import re
import time
from typing import Any

from mcp import ClientSession
from mcp.types import Tool

from app.models.schemas import ToolCall

AWS_CALL_TOOL_NAMES = frozenset(
    {
        "call_aws",
        "aws___call_aws",
        "aws__call_aws",
    }
)

# suggest_aws_commands was removed from the managed AWS MCP Server (GA release);
# documentation search replaced it.
AWS_SEARCH_DOC_TOOL_NAMES = frozenset(
    {
        "search_documentation",
        "aws___search_documentation",
        "knowledge___search_documentation",
    }
)

CLI_VERB_LABELS: dict[str, str] = {
    "run-instances": "Create EC2 instance",
    "terminate-instances": "Terminate EC2 instance",
    "stop-instances": "Stop EC2 instance",
    "start-instances": "Start EC2 instance",
    "create-tags": "Tag resource",
    "delete-tags": "Remove tags",
    "create-bucket": "Create S3 bucket",
    "delete-bucket": "Delete S3 bucket",
    "create-db-instance": "Create RDS instance",
    "delete-db-instance": "Delete RDS instance",
    "create-function": "Create Lambda function",
    "delete-function": "Delete Lambda function",
    "create-table": "Create DynamoDB table",
    "delete-table": "Delete DynamoDB table",
}

# Ops that start with create- but do not create a new primary resource.
CREATE_PREFIX_EXCEPTIONS: dict[str, tuple[str, str]] = {
    "create-tags": (
        "Tag resource",
        "This will add or update tags on the specified resource.",
    ),
    "create-tags-batch": (
        "Tag resources",
        "This will add or update tags on the specified resources.",
    ),
    "create-network-interface-permission": (
        "Grant network interface permission",
        "This will grant a permission on an existing network interface.",
    ),
    "create-snapshot": (
        "Create EBS snapshot",
        "This will create a snapshot of the specified volume.",
    ),
    "create-image": (
        "Create AMI",
        "This will create an AMI from the specified instance.",
    ),
}

DESTRUCTIVE_PATTERNS = re.compile(
    r"\b(delete|terminate|remove|destroy|drop|purge|deregister|release|disable|revoke)\b",
    re.IGNORECASE,
)

DESTRUCTIVE_CLI_PATTERNS = re.compile(
    r"\baws\s+\S+\s+(delete|terminate|remove|destroy|deregister|release|revoke-)\S*",
    re.IGNORECASE,
)

WRITE_CLI_PATTERNS = re.compile(
    r"\baws\s+\S+\s+(run-instances|create-|put-|update-|start-|stop-|modify-|attach-|detach-|allocate-|associate-|disassociate-|authorize-|register-)\S*",
    re.IGNORECASE,
)

READ_QUERY_PATTERNS = re.compile(
    r"\b(list|show|get|describe|what|which|any|all my|how many|display|view)\b",
    re.IGNORECASE,
)


def find_aws_call_tool(tools: list[Tool]) -> Tool | None:
    by_name = {tool.name: tool for tool in tools}
    for name in AWS_CALL_TOOL_NAMES:
        if name in by_name:
            return by_name[name]
    for tool in tools:
        lowered = tool.name.lower()
        if "call_aws" in lowered or lowered.endswith("call_aws"):
            return tool
    return None


def find_search_doc_tool(tools: list[Tool]) -> Tool | None:
    by_name = {tool.name: tool for tool in tools}
    for name in AWS_SEARCH_DOC_TOOL_NAMES:
        if name in by_name:
            return by_name[name]
    for tool in tools:
        if "search_documentation" in tool.name.lower():
            return tool
    return None


def is_call_aws_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    if tool_name in AWS_CALL_TOOL_NAMES:
        return True
    return "call_aws" in lowered or lowered.endswith("call_aws")


def _tool_base_name(name: str) -> str:
    return name.lower().rsplit("___", 1)[-1]


def resolve_tool_name(tool_name: str, tools: list[Tool]) -> str | None:
    """Map a model-provided tool name to the actual (possibly prefixed) MCP tool name.

    Small models often drop or invent the server prefix (e.g. calling
    'search_documentation' or 'knowledge___search_documentation' when the server
    exposes 'aws___search_documentation').
    """
    names = [tool.name for tool in tools]
    if tool_name in names:
        return tool_name
    base = _tool_base_name(tool_name)
    for name in names:
        if _tool_base_name(name) == base:
            return name
    return None


def build_action_summary(cli_command: str) -> tuple[str, str]:
    """Return (label, summary) describing what the CLI command will do."""
    parts = cli_command.split()
    service = parts[1] if len(parts) > 1 else "aws"
    operation = parts[2] if len(parts) > 2 else "command"

    if operation in CREATE_PREFIX_EXCEPTIONS:
        return CREATE_PREFIX_EXCEPTIONS[operation]

    label = CLI_VERB_LABELS.get(operation)
    if not label:
        verb = operation.replace("-", " ")
        if operation.startswith("create-") or operation.startswith("run-"):
            label = f"Create {service.upper()} resource"
        elif operation.startswith("delete-") or operation.startswith("terminate-"):
            label = f"Delete {service.upper()} resource"
        elif operation.startswith("update-") or operation.startswith("modify-"):
            label = f"Update {service.upper()} resource"
        else:
            label = f"{service.upper()} {verb}"

    summary = f"This will run `{cli_command}` against your AWS account."
    if operation == "run-instances":
        summary = "This will launch a new EC2 instance with the specified configuration."
    elif operation.startswith("create-bucket"):
        summary = "This will create a new S3 bucket."
    elif operation.startswith("terminate-"):
        summary = "This will permanently terminate the specified EC2 instance(s)."
    elif operation.startswith("delete-tags"):
        summary = "This will remove tags from the specified resource."
    elif operation.startswith("delete-"):
        summary = f"This will permanently delete the specified {service.upper()} resource."
    elif operation.startswith("create-"):
        summary = f"This will create a new {service.upper()} resource."

    return label, summary


def mcp_tools_to_llm(tools: list[Tool]) -> list[dict[str, Any]]:
    """Expose call_aws + search_documentation so models can look up CLI syntax."""
    selected: list[Tool] = []
    call_aws = find_aws_call_tool(tools)
    if call_aws:
        selected.append(call_aws)
    search_doc = find_search_doc_tool(tools)
    if search_doc and search_doc not in selected:
        selected.append(search_doc)
    if not selected:
        selected = tools[:3]

    llm_tools: list[dict[str, Any]] = []
    for tool in selected:
        schema = tool.inputSchema or {"type": "object", "properties": {}}
        llm_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (tool.description or tool.name)[:1200],
                    "parameters": schema,
                },
            }
        )
    return llm_tools


def parse_tool_call(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fn = raw.get("function") or {}
    tool_name = fn.get("name") or raw.get("name", "")
    raw_args = fn.get("arguments") if fn else raw.get("arguments")
    if raw_args is None:
        arguments: dict[str, Any] = {}
    elif isinstance(raw_args, str):
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            arguments = {"cli_command": raw_args}
    elif isinstance(raw_args, dict):
        arguments = raw_args
    else:
        arguments = {}
    return tool_name, arguments


def get_cli_command(arguments: dict[str, Any]) -> str | None:
    cli_command = arguments.get("cli_command") or arguments.get("command")
    if isinstance(cli_command, str):
        return cli_command
    if isinstance(cli_command, list):
        return " ".join(str(part) for part in cli_command)
    return None


def set_cli_command(arguments: dict[str, Any], cli_command: str) -> None:
    key = "cli_command" if "cli_command" in arguments or "command" not in arguments else "command"
    arguments[key] = cli_command


def sanitize_cli_command(cli_command: str) -> str:
    """Fix common invalid AWS CLI patterns produced by small local models."""
    normalized = " ".join(cli_command.split())
    if "run-instances" in normalized:
        normalized = re.sub(r"\s--tags\b", " --tag-specifications", normalized)
    return normalized


def is_write_cli_command(cli_command: str) -> bool:
    return bool(WRITE_CLI_PATTERNS.search(cli_command))


def is_read_only_user_query(message: str) -> bool:
    return bool(READ_QUERY_PATTERNS.search(message))


def read_only_fallback_command(message: str, region: str) -> str | None:
    """Return a safe read-only CLI command when the model picks a write op for a read query."""
    lowered = message.lower()
    if "s3" in lowered and "bucket" in lowered:
        return "aws s3api list-buckets"
    if "ec2" in lowered or "instance" in lowered:
        return f"aws ec2 describe-instances --region {region}"
    if "lambda" in lowered:
        return f"aws lambda list-functions --region {region}"
    if "rds" in lowered:
        return f"aws rds describe-db-instances --region {region}"
    return None


def coerce_read_only_command(message: str, region: str, cli_command: str) -> str:
    if is_read_only_user_query(message) and is_write_cli_command(cli_command):
        fallback = read_only_fallback_command(message, region)
        if fallback:
            return fallback
    return sanitize_cli_command(cli_command)


def extract_tool_output(result: Any) -> str:
    if result is None:
        return ""
    if hasattr(result, "content") and result.content:
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(block))
        return "\n".join(parts)
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    return str(result)


def is_destructive_tool_call(tool_name: str, arguments: dict[str, Any]) -> bool:
    if DESTRUCTIVE_PATTERNS.search(tool_name):
        return True

    serialized = json.dumps(arguments, default=str)
    if DESTRUCTIVE_PATTERNS.search(serialized):
        return True

    cli_command = get_cli_command(arguments)
    if cli_command and DESTRUCTIVE_CLI_PATTERNS.search(cli_command):
        return True

    return False


def is_write_tool_call(tool_name: str, arguments: dict[str, Any]) -> bool:
    if is_destructive_tool_call(tool_name, arguments):
        return False
    cli_command = get_cli_command(arguments)
    return bool(cli_command and is_write_cli_command(cli_command))


def build_action_resource(arguments: dict[str, Any], *, summary: str | None = None) -> dict[str, str]:
    resource: dict[str, str] = {}
    cli_command = get_cli_command(arguments)
    if summary:
        resource["Summary"] = summary
    if cli_command:
        resource["Command"] = cli_command

    for key, value in arguments.items():
        if key in {"cli_command", "command"}:
            continue
        resource[key.replace("_", " ").title()] = str(value)

    if not resource:
        resource["Warning"] = "This operation may modify AWS resources."
    return resource


def tool_call_label(tool_name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    cli_command = get_cli_command(arguments)
    if cli_command:
        return "AWS CLI", cli_command
    return tool_name, json.dumps(arguments, default=str)[:200]


def is_recoverable_tool_error(output: str) -> bool:
    lowered = output.lower()
    return "validation_failures" in lowered or "error while validating" in lowered


TOOL_ERROR_MARKERS = (
    "error calling tool",
    "error while executing the command",
    "error while validating the command",
    "parameter validation failed",
    "validation_failures",
    "an error occurred",
    "missing required parameter",
)


def is_tool_error_output(output: str) -> bool:
    """True when MCP tool output is an error message rather than a real result."""
    lowered = output.lower()
    return any(marker in lowered for marker in TOOL_ERROR_MARKERS)


async def invoke_mcp_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[ToolCall, str]:
    started = time.perf_counter()
    label, detail = tool_call_label(tool_name, arguments)
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        output = extract_tool_output(result)
    except Exception as exc:
        output = str(exc)
    duration_ms = int((time.perf_counter() - started) * 1000)
    tool = ToolCall(label=label, detail=detail, durationMs=duration_ms, output=output[:8000] or None)
    return tool, output
