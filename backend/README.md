# DevBot Backend

FastAPI backend for DevBot. Connects to the managed **AWS MCP Server** via `mcp-proxy-for-aws`,
orchestrates **Amazon Bedrock** (Claude) for the agent loop, and implements the REST/NDJSON API
expected by the React frontend.

## Prerequisites

- Python 3.11+
- Valid AWS credentials (Access Key ID + Secret Access Key) with:
  - Permissions for the AWS resources you want to inspect or manage
  - Access to the managed AWS MCP Server
  - Amazon Bedrock model access for Claude Haiku 4.5 (enable in the Bedrock console, us-east-1)

## Setup

```bash
cd backend
python -m pip install -e .
```

Or install dependencies directly:

```bash
python -m pip install fastapi "uvicorn[standard]" pydantic-settings boto3 mcp mcp-proxy-for-aws httpx awscli
```

## Run

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, start the frontend:

```bash
cd ../frontend
npm run dev
```

Open the Vite dev server (typically `http://localhost:5173`). The frontend proxies `/api/*` to `http://localhost:8000`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_MCP_ENDPOINT` | `https://aws-mcp.us-east-1.api.aws/mcp` | Managed AWS MCP Server URL |
| `AWS_MCP_SERVICE` | _(inferred)_ | SigV4 service name override |
| `AWS_MCP_REGION` | `us-east-1` | Region used for MCP proxy signing |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock inference profile ID |
| `BEDROCK_REGION` | `us-east-1` | Region for Bedrock Runtime |
| `LLM_TEMPERATURE` | `0.2` | Decoding temperature for tool calls |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Bind port |

Optional tuning:

- `AGENT_MAX_ITERATIONS` — max tool-calling loops per chat turn (default: 10)
- `ACTION_TTL_SECONDS` — pending write/destructive action expiry (default: 1800)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/aws/verify` | Validate AWS credentials via STS; connect MCP client |
| `POST` | `/api/chat` | Stream agent turn as NDJSON |
| `POST` | `/api/resources/scan` | Scan AWS account topology for resource map |
| `POST` | `/api/actions/{id}/confirm` | Execute staged write/destructive action |
| `POST` | `/api/actions/{id}/cancel` | Cancel staged action |
| `POST` | `/api/debug/check-logs` | Fetch CloudWatch logs, find errors, suggest hello-world fix (NDJSON) |
| `POST` | `/api/debug/chat` | Debugging chat with local `read_file` / `search_code` (NDJSON) |
| `GET` | `/health` | Health check |

## Architecture

1. **AWS verify** — `boto3` STS `GetCallerIdentity` validates credentials, then stores them in an in-memory session.
2. **MCP client** — `mcp-proxy-for-aws` connects to the managed AWS MCP Server with SigV4 signing.
3. **Chat agent** — Bedrock (Claude) receives MCP tools; tool calls go through MCP; write/destructive operations are staged for user confirmation.
4. **Resource scan** — Parallel read-only `call_aws` CLI commands via MCP build the topology for the frontend map.

## Troubleshooting

### Backend unavailable (frontend error)

Ensure uvicorn is running on port 8000:

```bash
curl http://127.0.0.1:8000/health
```

### AWS MCP connection failed

- Confirm credentials are valid and have IAM permissions for the AWS MCP Server
- Check `AWS_MCP_ENDPOINT` and `AWS_MCP_REGION`
- If SigV4 signing fails, set `AWS_MCP_SERVICE` explicitly (see [mcp-proxy-for-aws README](https://github.com/aws/mcp-proxy-for-aws))

### Bedrock model access denied / use case form

In the AWS console → Amazon Bedrock → Model access (region us-east-1), enable Anthropic Claude Haiku 4.5 and submit the Anthropic use case details form if prompted. Wait a few minutes after approval.

### Credentials lost after backend restart

Credentials are stored in memory only. Re-run AWS onboarding in the frontend after restarting the backend.

## Security Notes

- Binds to `127.0.0.1` by default (local-only)
- Credentials are never written to disk
- Write/destructive AWS operations require explicit user confirmation in the UI before execution
