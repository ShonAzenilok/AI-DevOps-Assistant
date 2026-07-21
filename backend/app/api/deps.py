from dataclasses import dataclass

from app.core.errors import credentials_required, service_unavailable
from app.core.session import SessionStore
from app.services.actions.registry import ActionRegistry
from app.services.bedrock.client import BedrockClient
from app.services.mcp.manager import McpClientManager


@dataclass
class AppState:
    session_store: SessionStore
    mcp_manager: McpClientManager
    bedrock_client: BedrockClient
    action_registry: ActionRegistry


def get_app_state() -> AppState:
    from app.main import app_state

    return app_state


def require_aws_session(*, require_mcp: bool = True) -> AppState:
    """Return app state after ensuring verified credentials (and MCP when needed)."""
    state = get_app_state()
    if state.session_store.credentials is None:
        raise credentials_required()
    if require_mcp and not state.mcp_manager.is_connected:
        raise service_unavailable("AWS MCP client is not connected. Re-verify credentials.")
    return state
