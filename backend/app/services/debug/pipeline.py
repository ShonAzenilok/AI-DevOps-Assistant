"""Check-logs state machine: CloudWatch → parse → code → Bedrock suggestion."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.services.bedrock.client import BedrockClient
from app.services.debug.code_reader import get_code_root, read_file_slice, search_code
from app.services.debug.parser import LogError, collect_errors, parse_log_events_payload
from app.services.mcp.manager import McpClientManager
from app.streaming.ndjson import ndjson_line

logger = logging.getLogger(__name__)

FIX_SYSTEM = """You are a debugging assistant for the hello-world Node/React app.
The user message already shows the CloudWatch error log and candidate files.
Your job:
1. Briefly confirm which log lines matter (you may quote a short line).
2. Name the exact file(s) to change using paths like `hello-world/server.js` (always include the hello-world/ prefix).
3. Explain the root cause.
4. Suggest a concrete code fix (markdown fenced diff or patched snippet) and label it with that exact file path.
Do not claim you applied the fix. Suggest only. Stay scoped to hello-world/."""


def _tool_event(label: str, detail: str, output: str | None = None, duration_ms: int | None = None) -> str:
    tool: dict[str, Any] = {"label": label, "detail": detail}
    if output is not None:
        tool["output"] = output[:8000]
    if duration_ms is not None:
        tool["durationMs"] = duration_ms
    return ndjson_line({"type": "tool", "tool": tool})


def _format_error_log_section(errors: list[LogError]) -> str:
    parts = ["## Error log (from CloudWatch)\n"]
    for i, err in enumerate(errors[:5], start=1):
        parts.append(f"### Error {i}\n")
        parts.append(f"```\n{err.message[:3000]}\n```\n")
    return "\n".join(parts)


def _format_files_section(file_refs: list[str]) -> str:
    if not file_refs:
        return (
            "## Files to inspect / change\n\n"
            "_No stack paths resolved yet — infer from the log and hello-world sources._\n"
        )
    lines = ["## Files to inspect / change\n"]
    for ref in file_refs:
        # ref is like server.js:25 → hello-world/server.js (line 25)
        if ":" in ref and not ref.startswith("hello-world"):
            path, _, rest = ref.partition(":")
            line_part = rest.split()[0] if rest else ""
            if line_part.isdigit():
                lines.append(f"- `hello-world/{path}` (around line {line_part})\n")
            else:
                lines.append(f"- `hello-world/{ref}`\n")
        elif ref.startswith("hello-world"):
            lines.append(f"- `{ref}`\n")
        else:
            lines.append(f"- `hello-world/{ref}`\n")
    return "".join(lines)


class ErrorFixPipeline:
    def __init__(self, mcp: McpClientManager, llm: BedrockClient) -> None:
        self.mcp = mcp
        self.llm = llm

    async def run(self) -> AsyncIterator[str]:
        try:
            async for line in self._run():
                yield line
        except Exception as exc:
            logger.exception("Check-logs pipeline failed")
            yield ndjson_line({"type": "error", "detail": str(exc)})
        finally:
            yield ndjson_line({"type": "done"})

    async def _run(self) -> AsyncIterator[str]:
        region = self.mcp.user_region or settings.aws_mcp_region
        lookback_ms = settings.debug_log_lookback_seconds * 1000
        start_ms = int(time.time() * 1000) - lookback_ms
        log_group = settings.debug_log_group

        # 1. Fetch logs
        cli = (
            f"aws logs filter-log-events --log-group-name {log_group} "
            f"--start-time {start_ms} --region {region} --output json"
        )
        t0 = time.perf_counter()
        try:
            raw = await self.mcp.call_aws_cli(cli, max_results=100)
        except Exception as exc:
            yield _tool_event(
                "Fetching CloudWatch logs",
                log_group,
                output=str(exc),
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            yield ndjson_line(
                {
                    "type": "token",
                    "text": f"Could not fetch logs from `{log_group}`: {exc}",
                }
            )
            return

        yield _tool_event(
            "Fetching CloudWatch logs",
            f"{log_group} (last {settings.debug_log_lookback_seconds // 60} min)",
            output=raw[:2000] or "(empty)",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        # 2. Parse errors
        t1 = time.perf_counter()
        events = parse_log_events_payload(raw)
        errors = collect_errors(events)
        scan_output = (
            "\n\n----------\n\n".join(e.message[:2000] for e in errors)
            if errors
            else "No error signatures"
        )
        yield _tool_event(
            "Scanning for errors",
            f"{len(events)} events → {len(errors)} unique error(s)",
            output=scan_output,
            duration_ms=int((time.perf_counter() - t1) * 1000),
        )

        if not errors:
            yield ndjson_line(
                {
                    "type": "token",
                    "text": (
                        f"All clear — no matching errors in `{log_group}` "
                        f"over the last hour "
                        f"(looked for ERROR, TypeError, CRASH_TEST, Exception, etc.)."
                    ),
                }
            )
            return

        # 3–4. Locate + read code
        code_chunks: list[str] = []
        root = get_code_root()
        t2 = time.perf_counter()
        read_notes: list[str] = []

        for err in errors[:5]:
            targets = list(err.stack_files)
            if not targets:
                for token in ("CRASH_TEST", "boom.crash", "TypeError", err.signature[:40]):
                    hits = search_code(token, max_hits=5)
                    for rel, line, _ in hits:
                        targets.append((rel, line))
                    if targets:
                        break

            for rel, line in targets[:3]:
                try:
                    chunk = read_file_slice(rel, line=line, context=25)
                    code_chunks.append(chunk)
                    read_notes.append(f"{rel}:{line}")
                except (ValueError, FileNotFoundError, OSError) as exc:
                    read_notes.append(f"{rel}: {exc}")

        if not code_chunks and root.is_dir():
            for token in ("crash", "dani", "CRASH_TEST"):
                hits = search_code(token, max_hits=8)
                for rel, line, _ in hits:
                    try:
                        code_chunks.append(read_file_slice(rel, line=line, context=25))
                        read_notes.append(f"{rel}:{line}")
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                if code_chunks:
                    break

        label = "Reading code" if code_chunks else "Searching hello-world"

        yield _tool_event(
            label,
            str(root),
            output="\n".join(read_notes) or "No matching source files",
            duration_ms=int((time.perf_counter() - t2) * 1000),
        )

        # Showcase logs + implicated files in the chat before the model fix
        file_refs: list[str] = []
        for n in read_notes:
            # Keep "server.js:25", skip notes that are error strings
            if ":" in n and not n.lower().startswith("file not") and "escapes" not in n.lower():
                path_part = n.split(":", 1)[0]
                if "/" in path_part or path_part.endswith((".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs")):
                    if n not in file_refs:
                        file_refs.append(n)
        for err in errors[:5]:
            for rel, line in err.stack_files:
                ref = f"{rel}:{line}"
                if ref not in file_refs:
                    file_refs.append(ref)

        preamble = (
            f"Found **{len(errors)}** error(s) in `{log_group}`.\n\n"
            + _format_error_log_section(errors)
            + "\n"
            + _format_files_section(file_refs)
            + "\n## Suggested fix\n\n"
        )
        yield ndjson_line({"type": "token", "text": preamble})

        # 5. Suggest fix
        error_block = "\n\n".join(
            f"### {e.signature}\n```\n{e.message[:2500]}\n```" for e in errors[:5]
        )
        files_for_prompt = (
            ", ".join(
                f"`hello-world/{r.split(':', 1)[0]}`" if not r.startswith("hello-world") else f"`{r}`"
                for r in file_refs
            )
            or "(infer from log)"
        )
        code_block = "\n\n".join(f"```\n{c}\n```" for c in code_chunks[:6]) or "(no source retrieved)"
        messages = [
            {"role": "system", "content": FIX_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"CloudWatch log group: `{log_group}`\n\n"
                    f"## Errors\n{error_block}\n\n"
                    f"## Likely files to change\n{files_for_prompt}\n\n"
                    f"## Code\n{code_block}\n\n"
                    "Write the suggested fix. Start with a line like "
                    "**File to change:** `hello-world/<path>` "
                    "for each file, then the root cause and the patch."
                ),
            },
        ]

        async for chunk in self.llm.chat_stream(messages, tools=None):
            msg = chunk.get("message") or {}
            content = msg.get("content") or ""
            if content:
                yield ndjson_line({"type": "token", "text": content})
