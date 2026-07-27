# DevBot

Local-first AI DevOps assistant for AWS. Chat with Claude on **Amazon Bedrock** to inspect and change your account through the managed **[AWS MCP Server](https://docs.aws.amazon.com/aws-mcp/)**. Write and destructive actions always require an explicit **Confirm** in the UI.

```
React (Vite)  →  FastAPI  →  Amazon Bedrock + AWS MCP Server
                  │
                  ├─ Chat agent (NDJSON stream, call_aws)
                  ├─ Local AWS CLI validation + staged Confirm
                  ├─ Resource map scan (deterministic CLI)
                  └─ Debugging (CloudWatch → hello-world → fix suggestion)
```

## Features

- **Onboarding** — enter Access Key / Secret / region; STS verifies the account and connects the managed AWS MCP Server
- **Chat** — Bedrock runs a ReAct loop with MCP tools (`call_aws` and documentation search). Reads run immediately; creates/updates/deletes are staged for Confirm / Cancel
- **CLI validation** — invalid AWS CLI is caught locally against `awscli` tables before it hits AWS
- **Resource map** — hierarchical region → VPC → subnet view built by fixed read-only CLI calls (not the LLM)
- **Debugging** — Check logs pulls CloudWatch (`my-container-logs`), finds errors, reads the jailed [`hello-world/`](hello-world/) sources, and suggests a fix; free-form debug chat can use local `read_file` / `search_code`
- **Docker Compose** — one command runs nginx (UI) + FastAPI (API)

## Prerequisites

Pick one way to run the app:

- **Docker** with Compose v2
- **Python 3.11+** and **Node.js 20+** for local development

AWS side:

- IAM credentials that can use the resources you care about
- Access to the [managed AWS MCP Server](https://docs.aws.amazon.com/aws-mcp/)
- Amazon Bedrock model access for **Claude Haiku 4.5** (typically enable in `us-east-1`)

## Quick start

### Docker (recommended)

```bash
docker compose up --build
```

- App UI: [http://localhost](http://localhost) (nginx proxies `/api` to the backend)
- Backend health: [http://localhost:8000/health](http://localhost:8000/health) or [http://localhost/health](http://localhost/health)

AWS keys are entered in the UI during onboarding — nothing else is required to start Compose.

The backend image embeds `hello-world/` source for Debugging. The standalone crash demo is built separately — see [`hello-world/README.md`](hello-world/README.md).

> If a root `.env` exists with freeform notes (not `KEY=value`), rename it before `docker compose`. Compose always tries to parse that file when present.

### Local (without Docker)

**1. Backend**

```bash
cd backend
python -m pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

**2. Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api/*` to the backend on port `8000`.

### First-run walkthrough

1. Complete onboarding with your AWS keys and region  
2. In **Chat**, try “List my S3 buckets” or “Show my running EC2 instances”  
3. For writes, review the Confirm card before anything runs in your account  
4. Open the **Resource map** and scan to see account topology  
5. Open **Debugging** → Check logs (needs CloudWatch log group `my-container-logs` and the hello-world app emitting errors — see [`hello-world/README.md`](hello-world/README.md))

## Project layout

```
├── backend/                 FastAPI + agent + MCP + Bedrock
│   ├── Dockerfile
│   ├── app/
│   │   ├── api/             HTTP routes (/aws, /chat, /resources, /actions, /debug)
│   │   ├── services/
│   │   │   ├── agent/       Chat orchestrator (ReAct loop)
│   │   │   ├── bedrock/     Converse API client
│   │   │   ├── mcp/         AWS MCP client + tool helpers
│   │   │   ├── aws_cli/     Local CLI validator
│   │   │   ├── actions/     Stage / confirm / retry writes
│   │   │   ├── resources/   Account scanner + map layout
│   │   │   └── debug/       Check logs pipeline + debug chat tools
│   │   └── streaming/       NDJSON helpers
│   └── tests/
├── frontend/                React + TypeScript + Vite + React Flow
│   ├── Dockerfile
│   └── nginx.conf           Proxies /api to backend in Compose
├── docker-compose.yml
├── hello-world/             Demo app (source also copied into backend image)
└── README.md                You are here
```

More backend detail (API list, troubleshooting): [`backend/README.md`](backend/README.md).

## How it works

**Chat**

1. Frontend `POST /api/chat` with your message and history  
2. Backend streams **NDJSON** (`token`, `tool`, `confirm`, `error`, `done`)  
3. Bedrock may call MCP tools; read CLI runs via `call_aws`  
4. Write/destructive CLI is **staged** — Confirm / Cancel in the UI  
5. Confirm executes the staged call (small self-correct retry if AWS rejects bad parameters)

**Resource map** — `POST /api/resources/scan` runs a fixed set of read-only AWS CLI commands through MCP and lays out the graph. The LLM is not involved.

**Debugging**

- **Check logs** — backend pipeline: CloudWatch → parse errors → search/read under `hello-world/` → Bedrock suggests a fix (`tools=None` on that last step)  
- **Debug chat** — Bedrock can call local `read_file` / `search_code` (path-jailed to `hello-world/`)

## Security notes

- Local runs bind to `127.0.0.1` by default  
- Credentials live in memory only — re-onboard after a backend restart  
- Never commit real AWS keys  
- Destructive AWS changes always go through the Confirm card  

## License

Hobby project — use at your own risk in accounts you own or are authorized to manage.
