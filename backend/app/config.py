from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # docker-compose frontend (nginx on :80)
        "http://localhost",
        "http://127.0.0.1",
    ]

    aws_mcp_endpoint: str = "https://aws-mcp.us-east-1.api.aws/mcp"
    # SigV4 service name for the managed AWS MCP Server (inferred from endpoint hostname).
    aws_mcp_service: str = "aws-mcp"
    aws_mcp_region: str = "us-east-1"

    # Cross-region inference profile ID (bare foundation-model IDs are rejected
    # for newer Claude models).
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_region: str = "us-east-1"
    # Low temperature keeps tool calls deterministic.
    llm_temperature: float = 0.2

    agent_max_iterations: int = 10
    action_ttl_seconds: int = 1800

    # Debugging / Check logs pipeline
    debug_log_group: str = "my-container-logs"
    debug_log_lookback_seconds: int = 3600
    # Empty = resolve repo-root/hello-world relative to this package.
    debug_code_root: str = ""


settings = Settings()
