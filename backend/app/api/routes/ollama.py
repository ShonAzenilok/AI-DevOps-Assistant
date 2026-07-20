from fastapi import APIRouter

from app.api.deps import get_app_state
from app.models.schemas import OllamaStatusResponse

router = APIRouter(prefix="/ollama", tags=["ollama"])


@router.get("/status", response_model=OllamaStatusResponse)
async def ollama_status() -> OllamaStatusResponse:
    state = get_app_state()
    instance_running, model_ready, model = await state.ollama_client.get_status()
    return OllamaStatusResponse(
        instanceRunning=instance_running,
        modelReady=model_ready,
        model=model,
    )
