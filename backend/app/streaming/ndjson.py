import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse


def ndjson_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


async def ndjson_response(events: AsyncIterator[str]) -> StreamingResponse:
    async def generate() -> AsyncIterator[bytes]:
        async for line in events:
            yield line.encode("utf-8")

    return StreamingResponse(generate(), media_type="application/x-ndjson")
