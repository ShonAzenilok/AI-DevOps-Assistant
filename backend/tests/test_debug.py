import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.debug.code_reader import get_code_root, read_file_slice, resolve_jailed_path
from app.services.debug.parser import collect_errors, is_error_message, parse_log_events_payload
from app.services.debug.pipeline import ErrorFixPipeline


def test_parse_log_events_payload_standard() -> None:
    raw = json.dumps(
        {
            "events": [
                {"timestamp": 1, "message": "info ok"},
                {"timestamp": 2, "message": "CRASH_TEST: boom\nTypeError: Cannot read"},
            ]
        }
    )
    events = parse_log_events_payload(raw)
    assert len(events) == 2
    assert events[1]["message"].startswith("CRASH_TEST")


def test_is_error_message_patterns() -> None:
    assert is_error_message("CRASH_TEST: intentional null dereference")
    assert is_error_message("TypeError: Cannot read properties of null")
    assert is_error_message("ERROR something failed")
    assert is_error_message("Unhandled Exception in handler")
    assert not is_error_message("hello-world listening on port 3000")


def test_collect_errors_dedupes_and_extracts_stack() -> None:
    events = [
        {
            "timestamp": 100,
            "message": (
                "CRASH_TEST: intentional null dereference for name=dani\n"
                "TypeError: Cannot read properties of null (reading 'crash')\n"
                "    at file:///app/hello-world/server.js:25:10"
            ),
        },
        {
            "timestamp": 200,
            "message": (
                "CRASH_TEST: intentional null dereference for name=dani\n"
                "TypeError: Cannot read properties of null (reading 'crash')\n"
                "    at file:///app/hello-world/server.js:25:10"
            ),
        },
        {"timestamp": 50, "message": "all good"},
    ]
    errors = collect_errors(events)
    assert len(errors) == 1
    assert "CRASH_TEST" in errors[0].signature
    assert any(rel.endswith("server.js") and line == 25 for rel, line in errors[0].stack_files)


def test_path_jail_rejects_escape() -> None:
    with pytest.raises(ValueError, match="escapes"):
        resolve_jailed_path("../backend/app/config.py")


def test_read_file_slice_server_js() -> None:
    root = get_code_root()
    assert root.name == "hello-world"
    text = read_file_slice("server.js", line=25, context=5)
    assert "CRASH_TEST" in text or "boom" in text
    assert "25|" in text or "server.js" in text


def test_pipeline_all_clear_with_mocked_mcp() -> None:
    mcp = MagicMock()
    mcp.user_region = "us-east-1"
    mcp.call_aws_cli = AsyncMock(
        return_value=json.dumps({"events": [{"timestamp": 1, "message": "listening on 3000"}]})
    )
    llm = MagicMock()

    async def no_stream(*_a: Any, **_k: Any) -> AsyncIterator[dict[str, Any]]:
        if False:  # pragma: no cover
            yield {}
        return

    llm.chat_stream = no_stream

    async def collect() -> str:
        lines: list[str] = []
        async for line in ErrorFixPipeline(mcp, llm).run():
            lines.append(line)
        return "".join(lines)

    joined = asyncio.run(collect())
    assert "Fetching CloudWatch logs" in joined
    assert "Scanning for errors" in joined
    assert "All clear" in joined
    assert '"type": "done"' in joined


def test_pipeline_suggests_fix_on_crash_log() -> None:
    mcp = MagicMock()
    mcp.user_region = "us-east-1"
    crash = (
        "CRASH_TEST: intentional null dereference for name=dani\n"
        "TypeError: Cannot read properties of null (reading 'crash')\n"
        "    at file:///C:/proj/hello-world/server.js:25:10"
    )
    mcp.call_aws_cli = AsyncMock(
        return_value=json.dumps({"events": [{"timestamp": 1, "message": crash}]})
    )

    async def fake_stream(*_a: Any, **_k: Any) -> AsyncIterator[dict[str, Any]]:
        yield {
            "message": {
                "role": "assistant",
                "content": "**File to change:** `hello-world/server.js`\nRoot cause: null deref on dani.",
            },
            "done": False,
        }
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

    llm = MagicMock()
    llm.chat_stream = fake_stream

    async def collect() -> str:
        lines: list[str] = []
        async for line in ErrorFixPipeline(mcp, llm).run():
            lines.append(line)
        return "".join(lines)

    joined = asyncio.run(collect())
    assert "Reading code" in joined or "Searching hello-world" in joined
    assert "Error log (from CloudWatch)" in joined
    assert "CRASH_TEST" in joined
    assert "hello-world/server.js" in joined
    assert "Root cause: null deref on dani." in joined
    assert '"type": "done"' in joined
