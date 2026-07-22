"""Parse CloudWatch log events into deduped error clusters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ERROR_PATTERN = re.compile(
    r"\b(ERROR|TypeError|CRASH_TEST|Exception|ReferenceError|SyntaxError|UnhandledPromiseRejection)\b",
    re.IGNORECASE,
)

# Node / generic stacks: path:line:col or path:line
STACK_FRAME = re.compile(
    r"(?:file:///?|(?:at\s+))?(?P<path>(?:[A-Za-z]:)?[^:\s()]+?[/\\][^:\s()]+?\.(?:js|ts|tsx|jsx|mjs|cjs)):(?P<line>\d+)(?::\d+)?",
    re.IGNORECASE,
)

HELLO_WORLD_HINT = re.compile(r"hello-world[/\\](?P<rel>[^\s:)]+\.(?:js|ts|tsx|jsx))", re.IGNORECASE)


@dataclass
class LogError:
    signature: str
    message: str
    timestamp: int | None = None
    stack_files: list[tuple[str, int]] = field(default_factory=list)  # (rel_or_name, line)


def parse_log_events_payload(raw: str) -> list[dict[str, Any]]:
    """Extract event dicts from filter-log-events CLI JSON (or loose text)."""
    text = raw.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return [{"message": text}]
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [{"message": text}]

    if isinstance(data, dict):
        events = data.get("events") or data.get("Events") or []
        if isinstance(events, list):
            return [e for e in events if isinstance(e, dict)]
        if "message" in data:
            return [data]
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    return []


def is_error_message(message: str) -> bool:
    return bool(ERROR_PATTERN.search(message or ""))


def extract_stack_files(message: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for match in STACK_FRAME.finditer(message or ""):
        path = match.group("path").replace("\\", "/")
        line = int(match.group("line"))
        # Prefer hello-world relative path when present
        hw = HELLO_WORLD_HINT.search(path)
        rel = hw.group("rel") if hw else path.rsplit("/", 1)[-1]
        key = (rel, line)
        if key not in seen:
            seen.add(key)
            found.append(key)
    return found


def _signature(message: str) -> str:
    # First non-empty line, truncated
    for line in (message or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:180]
    return "unknown-error"


def collect_errors(events: list[dict[str, Any]]) -> list[LogError]:
    """Filter error events and dedupe by signature."""
    by_sig: dict[str, LogError] = {}
    for event in events:
        message = str(event.get("message") or event.get("Message") or "")
        if not is_error_message(message):
            continue
        sig = _signature(message)
        ts_raw = event.get("timestamp") or event.get("Timestamp")
        ts = int(ts_raw) if ts_raw is not None else None
        stacks = extract_stack_files(message)
        if sig not in by_sig:
            by_sig[sig] = LogError(signature=sig, message=message[:4000], timestamp=ts, stack_files=stacks)
        else:
            existing = by_sig[sig]
            if len(message) > len(existing.message):
                existing.message = message[:4000]
            for item in stacks:
                if item not in existing.stack_files:
                    existing.stack_files.append(item)
    # Newest first when timestamps exist
    errors = list(by_sig.values())
    errors.sort(key=lambda e: e.timestamp or 0, reverse=True)
    return errors
