import logging

from fastapi import APIRouter

from app.api.deps import get_app_state
from app.core.errors import bad_request, format_error, service_unavailable
from app.models.schemas import AwsConfig, AwsVerifyResponse
from app.services.aws_verify import verify_aws_credentials

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/aws", tags=["aws"])


@router.post("/verify", response_model=AwsVerifyResponse)
async def verify_aws(config: AwsConfig) -> AwsVerifyResponse:
    state = get_app_state()
    try:
        stored = verify_aws_credentials(config)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc

    state.session_store.set_credentials(stored)
    try:
        await state.mcp_manager.connect(stored)
    except Exception as exc:
        state.session_store.clear()
        logger.exception("Failed to connect to AWS MCP Server")
        raise service_unavailable(
            f"Could not connect to AWS MCP Server: {format_error(exc)}"
        ) from exc

    return AwsVerifyResponse(accountId=stored.account_id)
