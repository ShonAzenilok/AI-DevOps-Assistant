from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.models.schemas import ActionResultResponse, PendingAction, StagedMcpCall
from app.services.mcp.tools import invoke_mcp_tool

logger = logging.getLogger(__name__)


class ActionRegistry:
    """Stores destructive MCP calls until the user confirms or cancels."""

    def __init__(self) -> None:
        self._pending: dict[str, tuple[StagedMcpCall, datetime]] = {}

    def _purge_expired(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.action_ttl_seconds)
        expired = [action_id for action_id, (_, created) in self._pending.items() if created < cutoff]
        for action_id in expired:
            del self._pending[action_id]

    def stage(self, call: StagedMcpCall) -> PendingAction:
        self._purge_expired()
        action_id = str(uuid.uuid4())
        self._pending[action_id] = (call, datetime.now(UTC))
        return PendingAction(
            id=action_id,
            label=call.label,
            detail=call.detail,
            resource=call.resource,
            status="pending",
        )

    def get(self, action_id: str) -> StagedMcpCall | None:
        self._purge_expired()
        entry = self._pending.get(action_id)
        return entry[0] if entry else None

    async def confirm(self, action_id: str, mcp_session: Any) -> ActionResultResponse:
        call = self.get(action_id)
        if call is None:
            return ActionResultResponse(status="failed", summary="Action not found or expired.")

        del self._pending[action_id]
        try:
            tool, output = await invoke_mcp_tool(mcp_session, call.tool_name, call.arguments)
            return ActionResultResponse(
                status="executed",
                summary=f"Deleted — {call.detail}",
                output=tool.output or output[:8000],
            )
        except Exception as exc:
            logger.exception("Failed to execute staged action %s", action_id)
            return ActionResultResponse(status="failed", summary=str(exc))

    def cancel(self, action_id: str) -> ActionResultResponse:
        call = self.get(action_id)
        if call is None:
            return ActionResultResponse(status="failed", summary="Action not found or expired.")
        del self._pending[action_id]
        return ActionResultResponse(status="cancelled", summary=f"Cancelled — {call.detail}")
