from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import User
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit

from app.quest.dao import BlocksDAO
from app.logger import logger
from app.quest.schemas import BlockFilter

router = APIRouter()

@router.get("/")
async def get_all_quest_blocks(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """
    Получает все блоки квеста
    """
    # Пример данных блоков
    blocks_dao = BlocksDAO(session)

    filter_model = BlockFilter(language_id=1)
    blocks = await blocks_dao.find_all(filters=filter_model)
    example_blocks = [{
        "id": block.id,
        "title": block.title,
        "language_id": block.language_id
    } for block in blocks]

    logger.info(example_blocks)

    response = JSONResponse(
        content={
            "ok": True,
            "message": "Blocks load successful",
            "blocks": example_blocks,
            # "user": {
            #     "id": user.id,
            #     "telegram_id": user.telegram_id,
            #     "full_name": user.full_name,
            #     "telegram_username": user.telegram_username,
            #     "is_active": user.role_id is not None
            # }
        }
    )
    return response