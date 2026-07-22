"""Safe file reads under the hello-world code root."""

from __future__ import annotations

from pathlib import Path

from app.config import settings

# backend/app/services/debug/code_reader.py → parents[4] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


def get_code_root() -> Path:
    if settings.debug_code_root.strip():
        root = Path(settings.debug_code_root).expanduser().resolve()
    else:
        root = (_REPO_ROOT / "hello-world").resolve()
    return root


def resolve_jailed_path(rel_or_name: str) -> Path:
    """Resolve a path under the code root; raise ValueError if outside the jail."""
    root = get_code_root()
    if not root.is_dir():
        raise ValueError(f"Code root does not exist: {root}")

    cleaned = rel_or_name.replace("\\", "/").strip().lstrip("/")
    # Strip leading hello-world/ if present in stacks
    lower = cleaned.lower()
    if lower.startswith("hello-world/"):
        cleaned = cleaned[len("hello-world/") :]

    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes code root: {rel_or_name}") from exc
    return candidate


def read_file_slice(rel_or_name: str, *, line: int | None = None, context: int = 20) -> str:
    path = resolve_jailed_path(rel_or_name)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {rel_or_name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if line is None or line < 1:
        # Cap large files
        if len(lines) > 200:
            return "\n".join(lines[:200]) + f"\n\n... ({len(lines) - 200} more lines)"
        return text
    idx = line - 1
    start = max(0, idx - context)
    end = min(len(lines), idx + context + 1)
    numbered = [f"{i + 1:>4}| {lines[i]}" for i in range(start, end)]
    header = f"# {path.relative_to(get_code_root()).as_posix()} (lines {start + 1}-{end})\n"
    return header + "\n".join(numbered)


def search_code(query: str, *, max_hits: int = 12) -> list[tuple[str, int, str]]:
    """Return (rel_path, line_no, line_text) hits under the code root."""
    root = get_code_root()
    if not root.is_dir():
        return []
    needle = query.strip()
    if not needle:
        return []
    needle_lower = needle.lower()
    hits: list[tuple[str, int, str]] = []
    skip_dirs = {".git", "node_modules", "dist", ".vite"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in {".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".json", ".css", ".html", ".md"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if needle_lower in line.lower():
                rel = path.relative_to(root).as_posix()
                hits.append((rel, i, line.strip()[:200]))
                if len(hits) >= max_hits:
                    return hits
    return hits
