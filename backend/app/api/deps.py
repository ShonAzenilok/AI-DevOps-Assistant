from dataclasses import dataclass

from app.core.session import SessionStore
from app.services.actions.registry import ActionRegistry
from app.services.mcp.manager import McpClientManager
from app.services.ollama.client import OllamaClient


@dataclass
class AppState:
    session_store: SessionStore
    mcp_manager: McpClientManager
    ollama_client: OllamaClient
    action_registry: ActionRegistry


def get_app_state() -> AppState:
    from app.main import app_state

    return app_state
