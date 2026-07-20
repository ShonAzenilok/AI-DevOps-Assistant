from fastapi import APIRouter

from app.api.deps import get_app_state
from app.core.errors import credentials_required, service_unavailable
from app.models.schemas import ChatRequest, ScanResult
from app.services.resources.scanner import ResourceScanner

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("/scan", response_model=ScanResult)
async def scan_resources() -> ScanResult:
    state = get_app_state()
    credentials = state.session_store.credentials
    if credentials is None:
        raise credentials_required()
    if not state.mcp_manager.is_connected:
        raise service_unavailable("AWS MCP client is not connected. Re-verify credentials.")

    scanner = ResourceScanner(state.mcp_manager)
    return await scanner.scan(credentials)
