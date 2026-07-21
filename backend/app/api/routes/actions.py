import logging

from fastapi import APIRouter

from app.api.deps import require_aws_session
from app.models.schemas import ActionResultResponse
from app.services.actions.executor import execute_with_retry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/{action_id}/confirm", response_model=ActionResultResponse)
async def confirm_action(action_id: str) -> ActionResultResponse:
    state = require_aws_session()
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
    state = require_aws_session(require_mcp=False)
    return state.action_registry.cancel(action_id)
