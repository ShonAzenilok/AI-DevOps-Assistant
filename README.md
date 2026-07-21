# DevBot

Local-first AI DevOps assistant for AWS. Chat with Claude (via Amazon Bedrock) to inspect and manage your account; write and destructive actions always require an explicit Confirm in the UI.

```
React (Vite)  →  FastAPI  →  Amazon Bedrock + AWS MCP Server
                  │
                  ├─ Chat agent (NDJSON stream)
                  ├─ Local AWS CLI validation
                  ├─ Staged writes → Confirm / Cancel
                  └─ Resource map scan
```

## Features

- **Onboarding** — enter Access Key / Secret / region; STS verifies the account and connects the managed AWS MCP Server
- **Chat agent** — Bedrock drives a ReAct loop; tools are MCP `call_aws` and documentation search.
- **Safe writes** — create / update / delete commands are staged until you click Confirm.
- **CLI validation** — invalid commands are caught locally against `awscli` tables before they hit AWS
- **Resource map** — hierarchical region → VPC → subnet view of common AWS resources

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** (for the frontend)
- **AWS credentials** with permission to use the resources you care about, plus:
  - Access to the [managed AWS MCP Server](https://docs.aws.amazon.com/aws-mcp/)
  - Amazon Bedrock model access for Claude Haiku 4.5 (enable in the Bedrock console, typically `us-east-1`)

## Quick start

### 1. Backend

```bash
cd backend
python -m pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api/*` to the backend on port `8000`.

### 3. Use the app

1. Complete onboarding with your AWS keys and region  
2. Chat for read-only questions (e.g. “list my S3 buckets”)  
3. For writes, review the Confirm card before anything runs in your account  
4. Open the resource map and scan to see account topology  

## Project layout

```
├── backend/                 FastAPI + agent + MCP + Bedrock
│   ├── app/
│   │   ├── api/             HTTP routes (/aws, /chat, /resources, /actions)
│   │   ├── services/
│   │   │   ├── agent/       Chat orchestrator (ReAct loop)
│   │   │   ├── bedrock/     Converse API client
│   │   │   ├── mcp/         AWS MCP client + tool helpers
│   │   │   ├── aws_cli/     Local CLI validator
│   │   │   ├── actions/     Stage / confirm / retry writes
│   │   │   └── resources/   Account scanner + map layout
│   │   └── streaming/       NDJSON helpers
│   └── tests/
├── frontend/                React + TypeScript + Vite + React Flow
└── README.md                You are here
```

More backend detail (env vars, endpoints, troubleshooting): [`backend/README.md`](backend/README.md).

## How chat works (short version)

1. Frontend `POST /api/chat` with your message and history  
2. Backend streams **NDJSON** events (`token`, `tool`, `confirm`, `error`, `done`)  
3. Bedrock may call MCP tools; read commands run immediately via `call_aws`  
4. Write/destructive commands are **staged** — UI shows Confirm / Cancel  
5. Confirm runs the command (with a small self-correct retry loop if AWS rejects bad parameters)

## Environment variables

Optional. Defaults work for local use. Set in `backend/.env` or the shell:

| Variable | Default | Purpose |
|----------|---------|---------|
| `BEDROCK_MODEL_ID` | Claude Haiku 4.5 inference profile | Model for the agent |
| `BEDROCK_REGION` | `us-east-1` | Bedrock Runtime region |
| `AWS_MCP_ENDPOINT` | Managed AWS MCP URL | MCP server endpoint |
| `AWS_MCP_REGION` | `us-east-1` | SigV4 signing region for MCP |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Backend bind address |

Full list: [`backend/README.md`](backend/README.md#environment-variables).

## Tests

```bash
cd backend
python -m pytest -q
```

## Security notes

- Binds to `127.0.0.1` by default (local only)
- Credentials live in memory only — re-onboard after a backend restart
- Never commit `.env` files or real AWS keys
- Destructive AWS changes always go through the Confirm card

## License

Hobby project — use at your own risk in accounts you own or are authorized to manage.
