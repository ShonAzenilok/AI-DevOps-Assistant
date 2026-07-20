from fastapi import APIRouter

from app.api.routes import actions, aws, chat, resources

router = APIRouter()
router.include_router(chat.router)
router.include_router(aws.router)
router.include_router(resources.router)
router.include_router(actions.router)
