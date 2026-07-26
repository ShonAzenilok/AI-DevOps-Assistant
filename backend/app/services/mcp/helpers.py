"""Small shared helpers for CLI parsing, tool args, and output truncation."""

from __future__ import annotations

import json
from typing import Any


def parse_cli_head(cli_command: str) -> tuple[str, str]:
    """Return (service, operation) from an `aws <service> <operation> ...` command."""
    parts = cli_command.split()
    service = parts[1] if len(parts) > 1 else "aws"
    operation = parts[2] if len(parts) > 2 else "command"
    return service, operation


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """Normalize tool-call arguments from a dict, JSON string, or other value."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"cli_command": raw}
        return parsed if isinstance(parsed, dict) else {"cli_command": raw}
    if isinstance(raw, dict):
        return raw
    return {}


def truncate_output(text: str, limit: int = 8000) -> str:
    """Cap tool/action output length for NDJSON and API responses."""
    return text[:limit]


def pretty_print_json(text: str) -> str:
    """If text is JSON, return indented form; otherwise return unchanged."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return text
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, indent=2, ensure_ascii=False, default=str)
