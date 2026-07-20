# DevBot Backend

Local-first FastAPI backend for DevBot. Connects to the managed **AWS MCP Server** via `mcp-proxy-for-aws`, orchestrates **Ollama** for the agent loop, and implements the REST/NDJSON API expected by the React frontend.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) running locally with the model pulled:

```bash
ollama pull qwen3.5:4b
```

- Valid AWS credentials (Access Key ID + Secret Access Key) with permissions for the resources you want to inspect or manage

## Setup

```bash
cd backend
python -m pip install -e .
```

Or install dependencies directly:

```bash
python -m pip install fastapi "uvicorn[standard]" pydantic-settings boto3 mcp mcp-proxy-for-aws httpx
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
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Model name checked during onboarding |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Bind port |

Optional tuning:

- `AGENT_MAX_ITERATIONS` — max tool-calling loops per chat turn (default: 10)
- `ACTION_TTL_SECONDS` — pending destructive action expiry (default: 1800)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/aws/verify` | Validate AWS credentials via STS; connect MCP client |
| `GET` | `/api/ollama/status` | Check Ollama instance and model readiness |
| `POST` | `/api/chat` | Stream agent turn as NDJSON |
| `POST` | `/api/resources/scan` | Scan AWS account topology for resource map |
| `POST` | `/api/actions/{id}/confirm` | Execute staged destructive action |
| `POST` | `/api/actions/{id}/cancel` | Cancel staged destructive action |
| `GET` | `/health` | Health check |

## Architecture

1. **AWS verify** — `boto3` STS `GetCallerIdentity` validates credentials, then stores them in an in-memory session.
2. **MCP client** — `mcp-proxy-for-aws` connects to the managed AWS MCP Server with SigV4 signing.
3. **Chat agent** — Ollama receives MCP tools; tool calls go through MCP; destructive operations are staged for user confirmation.
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

### Ollama not ready

```bash
ollama serve
ollama pull qwen3.5:4b
curl http://localhost:11434/api/tags
```

### Credentials lost after backend restart

Credentials are stored in memory only. Re-run AWS onboarding in the frontend after restarting the backend.

## Security Notes

- Binds to `127.0.0.1` by default (local-only)
- Credentials are never written to disk
- Destructive AWS operations require explicit user confirmation in the UI before execution
