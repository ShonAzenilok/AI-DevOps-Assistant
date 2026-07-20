from collections.abc import AsyncIterator

from fastapi import APIRouter

from app.api.deps import get_app_state
from app.core.errors import credentials_required, service_unavailable
from app.models.schemas import ChatRequest
from app.services.ollama.agent import AgentOrchestrator
from app.streaming.ndjson import ndjson_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: ChatRequest):
    state = get_app_state()
    if state.session_store.credentials is None:
        raise credentials_required()
    if not state.mcp_manager.is_connected:
        raise service_unavailable("AWS MCP client is not connected. Re-verify credentials.")

    orchestrator = AgentOrchestrator(
        ollama=state.ollama_client,
        mcp=state.mcp_manager,
        actions=state.action_registry,
    )

    async def events() -> AsyncIterator[str]:
        async for line in orchestrator.run_turn(request.message, request.history):
            yield line

    return await ndjson_response(events())
