"""Local AWS CLI command validation using the awscli package's own command tables.

Catches invalid services, operations, and parameter names before a command is
staged for confirmation or sent to the AWS MCP server, so the model gets fast,
precise feedback instead of a slow late failure.
"""

from __future__ import annotations

import difflib
import logging
import shlex
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Global CLI options accepted on any operation (subset that matters here).
GLOBAL_OPTIONS = frozenset(
    {
        "--region",
        "--output",
        "--query",
        "--profile",
        "--endpoint-url",
        "--no-verify-ssl",
        "--no-paginate",
        "--max-items",
        "--starting-token",
        "--page-size",
        "--cli-read-timeout",
        "--cli-connect-timeout",
        "--no-cli-pager",
        "--color",
        "--debug",
        "--version",
    }
)

# Commands whose parameters bypass normal parsing; skip param validation.
PARSER_BYPASS_FLAGS = ("--cli-input-json", "--cli-input-yaml", "--generate-cli-skeleton")

# Custom high-level services whose subcommands don't follow the standard
# service/operation arg-table model (e.g. `aws s3 ls`). Validate service only.
CUSTOM_SERVICES = frozenset({"s3", "configure", "history", "deploy", "ddb", "emr", "opsworks"})


@dataclass
class CliValidationResult:
    ok: bool
    error: str | None = None
    valid_params: list[str] = field(default_factory=list)


class CliValidator:
    """Validates AWS CLI command strings against awscli's command tables."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._service_table: dict | None = None

    def _get_service_table(self) -> dict:
        with self._lock:
            if self._service_table is None:
                from awscli.clidriver import create_clidriver

                driver = create_clidriver()
                self._service_table = driver._get_command_table()
                logger.info("awscli command table loaded (%d services)", len(self._service_table))
            return self._service_table

    def validate(self, cli_command: str) -> CliValidationResult:
        """Check service/operation/params against awscli tables; never raises."""
        try:
            return self._validate(cli_command)
        except Exception as exc:
            # Never let validation crash the agent; treat as pass-through.
            logger.warning("CLI validation errored, allowing command: %s", exc)
            return CliValidationResult(ok=True)

    def _validate(self, cli_command: str) -> CliValidationResult:
        try:
            tokens = shlex.split(cli_command, posix=True)
        except ValueError as exc:
            return CliValidationResult(ok=False, error=f"Malformed command quoting: {exc}")

        if not tokens or tokens[0] != "aws":
            return CliValidationResult(ok=False, error='Command must start with "aws".')
        if len(tokens) < 2:
            return CliValidationResult(ok=False, error="Missing AWS service name.")

        if any(flag in cli_command for flag in PARSER_BYPASS_FLAGS):
            return CliValidationResult(ok=True)

        service_name = tokens[1]
        service_table = self._get_service_table()
        service = service_table.get(service_name)
        if service is None:
            close = difflib.get_close_matches(service_name, service_table.keys(), n=3)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            return CliValidationResult(
                ok=False, error=f"Unknown AWS service '{service_name}'.{hint}"
            )

        if service_name in CUSTOM_SERVICES:
            return CliValidationResult(ok=True)

        if len(tokens) < 3:
            return CliValidationResult(ok=False, error=f"Missing operation for service '{service_name}'.")

        operation_name = tokens[2]
        try:
            op_table = service._get_command_table()
        except AttributeError:
            return CliValidationResult(ok=True)

        operation = op_table.get(operation_name)
        if operation is None:
            close = difflib.get_close_matches(operation_name, op_table.keys(), n=5)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            return CliValidationResult(
                ok=False,
                error=f"Unknown operation '{operation_name}' for service '{service_name}'.{hint}",
            )

        try:
            arg_table = operation.arg_table
        except AttributeError:
            return CliValidationResult(ok=True)

        valid_params = sorted(f"--{name}" for name in arg_table)
        allowed = set(valid_params) | GLOBAL_OPTIONS
        # Boolean params generate --no-<name> variants.
        allowed |= {f"--no-{name}" for name in arg_table}

        bad_flags = [
            token
            for token in tokens[3:]
            if token.startswith("--") and token.split("=", 1)[0] not in allowed
        ]
        if bad_flags:
            return CliValidationResult(
                ok=False,
                error=(
                    f"Operation '{operation_name}' for service '{service_name}' does not "
                    f"support: {', '.join(bad_flags)}."
                ),
                valid_params=valid_params,
            )

        return CliValidationResult(ok=True, valid_params=valid_params)


cli_validator = CliValidator()
