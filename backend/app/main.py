import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import AppState
from app.api.router import router as api_router
from app.config import settings
from app.core.errors import format_error
from app.core.session import SessionStore
from app.services.actions.registry import ActionRegistry
from app.services.mcp.manager import McpClientManager
from app.services.ollama.client import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app_state = AppState(
    session_store=SessionStore(),
    mcp_manager=McpClientManager(),
    ollama_client=OllamaClient(),
    action_registry=ActionRegistry(),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("DevBot backend starting on %s:%s", settings.host, settings.port)
    yield
    await app_state.mcp_manager.disconnect()
    logger.info("DevBot backend stopped.")


app = FastAPI(title="DevBot Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error")
    return JSONResponse(status_code=500, content={"detail": format_error(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
