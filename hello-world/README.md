# Hello World (CloudWatch crash test)

Tiny React UI + Node/Express API. Submitting the name **dani** triggers an intentional null-dereference on the **server** so the stack appears in container stdout/stderr (what CloudWatch can ingest later on EC2).

A browser-only crash would only show in DevTools and would never reach CloudWatch.

## Local development

```bash
cd hello-world
npm install

# Terminal 1 — API on :3000
npm run dev:server

# Terminal 2 — Vite UI (proxies /api → :3000)
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

- Enter any name except dani → **Hello {name}**
- Enter **dani** → UI error; check the API terminal for `CRASH_TEST: intentional null dereference for name=dani` plus a TypeError stack

## Production (built UI + API on one port)

```bash
npm run build
npm start
```

App: http://127.0.0.1:3000

## Docker

```bash
docker build -t hello-world .
docker run --rm -p 3000:3000 hello-world
```

Then open http://127.0.0.1:3000 and try names as above. `docker logs` on the container shows the crash when you submit **dani**.

Wiring those logs into CloudWatch (agent or Docker log driver) is a later EC2 step.
