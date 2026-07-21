from collections.abc import AsyncIterator

from fastapi import APIRouter

from app.api.deps import require_aws_session
from app.models.schemas import ChatRequest
from app.services.agent.orchestrator import AgentOrchestrator
from app.streaming.ndjson import ndjson_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: ChatRequest):
    state = require_aws_session()
    orchestrator = AgentOrchestrator(
        llm=state.bedrock_client,
        mcp=state.mcp_manager,
        actions=state.action_registry,
    )

    async def events() -> AsyncIterator[str]:
        async for line in orchestrator.run_turn(request.message, request.history):
            yield line

    return await ndjson_response(events())
