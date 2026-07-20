from dataclasses import dataclass

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
