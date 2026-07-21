from __future__ import annotations

import logging
from contextlib import AsyncExitStack, suppress
from typing import Any

from botocore.credentials import Credentials
from mcp import ClientSession
from mcp.types import Tool
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from mcp_proxy_for_aws.utils import determine_service_name

from app.config import settings
from app.models.schemas import StoredAwsCredentials
from app.services.mcp.tools import extract_tool_output, find_aws_call_tool

logger = logging.getLogger(__name__)


class McpClientManager:
    """Maintains a long-lived MCP ClientSession to the managed AWS MCP Server."""

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._credentials: StoredAwsCredentials | None = None

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP client is not connected.")
        return self._session

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools)

    @property
    def user_region(self) -> str | None:
        return self._credentials.region if self._credentials else None

    async def connect(self, credentials: StoredAwsCredentials) -> None:
        await self.disconnect()
        self._credentials = credentials

        creds = Credentials(
            access_key=credentials.access_key_id,
            secret_key=credentials.secret_access_key,
        )

        aws_service = determine_service_name(settings.aws_mcp_endpoint, settings.aws_mcp_service)

        # Do not pass metadata= here — mcp-proxy-for-aws's metadata hook rewrites the
        # request body without updating Content-Length, which breaks MCP initialize.
        # Region is appended to each CLI command via ensure_cli_region() instead.
        kwargs: dict[str, Any] = {
            "endpoint": settings.aws_mcp_endpoint,
            "aws_service": aws_service,
            "aws_region": settings.aws_mcp_region,
            "credentials": creds,
            "timeout": 120,
        }

        stack = AsyncExitStack()
        try:
            read_stream, write_stream, _ = await stack.enter_async_context(
                aws_iam_streamablehttp_client(**kwargs)
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            tools_result = await session.list_tools()
            self._stack = stack
            self._session = session
            self._tools = list(tools_result.tools)
            logger.info(
                "Connected to AWS MCP Server with %d tools: %s",
                len(self._tools),
                ", ".join(tool.name for tool in self._tools),
            )
        except Exception:
            with suppress(Exception):
                await stack.aclose()
            raise

    async def disconnect(self) -> None:
        if self._stack is not None:
            with suppress(Exception):
                await self._stack.aclose()
        self._stack = None
        self._session = None
        self._tools = []
        self._credentials = None

    def ensure_cli_region(self, cli_command: str) -> str:
        if self._credentials and "--region" not in cli_command:
            return f"{cli_command} --region {self._credentials.region}"
        return cli_command

    async def call_aws_cli(self, cli_command: str, max_results: int | None = None) -> str:
        tool = find_aws_call_tool(self._tools)
        if tool is None:
            raise RuntimeError("AWS MCP server does not expose a call_aws tool.")

        cli_command = self.ensure_cli_region(cli_command)
        arguments: dict[str, Any] = {"cli_command": cli_command}
        if max_results is not None:
            arguments["max_results"] = max_results

        result = await self.session.call_tool(tool.name, arguments=arguments)
        return extract_tool_output(result)
