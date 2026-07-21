from fastapi import APIRouter

from app.api.deps import require_aws_session
from app.models.schemas import ScanResult
from app.services.resources.scanner import ResourceScanner

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("/scan", response_model=ScanResult)
async def scan_resources() -> ScanResult:
    state = require_aws_session()
    credentials = state.session_store.credentials
    assert credentials is not None  # require_aws_session guarantees this
    scanner = ResourceScanner(state.mcp_manager)
    return await scanner.scan(credentials)
