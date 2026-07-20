import logging

from fastapi import APIRouter

from app.api.deps import get_app_state
from app.core.errors import credentials_required, service_unavailable
from app.models.schemas import ActionResultResponse
from app.services.actions.executor import execute_with_retry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/{action_id}/confirm", response_model=ActionResultResponse)
async def confirm_action(action_id: str) -> ActionResultResponse:
    state = get_app_state()
    if state.session_store.credentials is None:
        raise credentials_required()
    if not state.mcp_manager.is_connected:
        raise service_unavailable("AWS MCP client is not connected. Re-verify credentials.")

    call = state.action_registry.take(action_id)
    if call is None:
        return ActionResultResponse(status="failed", summary="Action not found or expired.")

    try:
        return await execute_with_retry(call, state.mcp_manager, state.bedrock_client)
    except Exception as exc:
        logger.exception("Failed to execute staged action %s", action_id)
        return ActionResultResponse(status="failed", summary=str(exc))


@router.post("/{action_id}/cancel", response_model=ActionResultResponse)
async def cancel_action(action_id: str) -> ActionResultResponse:
    state = get_app_state()
    if state.session_store.credentials is None:
        raise credentials_required()
    return state.action_registry.cancel(action_id)
