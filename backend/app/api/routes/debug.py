from collections.abc import AsyncIterator

from fastapi import APIRouter

from app.api.deps import require_aws_session
from app.models.schemas import ChatRequest
from app.services.debug.chat import DebugChatOrchestrator
from app.services.debug.pipeline import ErrorFixPipeline
from app.streaming.ndjson import ndjson_response

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/check-logs")
async def check_logs():
    state = require_aws_session()
    pipeline = ErrorFixPipeline(state.mcp_manager, state.bedrock_client)

    async def events() -> AsyncIterator[str]:
        async for line in pipeline.run():
            yield line

    return await ndjson_response(events())


@router.post("/chat")
async def debug_chat(request: ChatRequest):
    state = require_aws_session()
    orchestrator = DebugChatOrchestrator(state.bedrock_client)

    async def events() -> AsyncIterator[str]:
        async for line in orchestrator.run_turn(request.message, request.history):
            yield line

    return await ndjson_response(events())
