from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dao import CommandsDAO, UsersDAO
from app.auth.models import User
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit

from app.quest.dao import BlocksDAO, QuestionsDAO, AnswersDAO
from app.logger import logger
from app.quest.schemas import BlockFilter, FindAnswersForQuestion, FindQuestionsForBlock

router = APIRouter()

@router.get("/")
async def get_all_quest_blocks(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user),
    include_riddles: bool = False
):
    """
    Получает все блоки квеста
    """
    # Получить язык команды пользователя
    users_dao = UsersDAO(session)

    # TODO: Подумать над номером мероприятия
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        logger.error(f"Пользователь {user.id} не состоит ни в одной команде для стандартного мероприятия")
        return

    # Пример данных блоков
    blocks_dao = BlocksDAO(session)

    # TODO: По-хорошему это надо закэшировать
    blocks = await blocks_dao.find_all(filters=BlockFilter(language_id=command.language_id))
    example_blocks = [{
        "id": block.id,
        "title": block.title,
        "language_id": block.language_id
    } for block in blocks]

    logger.info(example_blocks)

    response_data = {
        "ok": True,
        "message": "Blocks load successful",
        "blocks": [{
            "id": block.id,
            "title": block.title,
            "language_id": block.language_id
        } for block in blocks]
    }

    if include_riddles:
        # Добавляем загадки только если явно запрошено
        for block in response_data['blocks']:
            block['riddles'] = await get_riddles_for_block(block['id'], session)

    response = JSONResponse(content=response_data)
    return response

@router.get("/{block_id}")
async def get_quest_block(
    block_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """
    Получает конкретный блок квеста по его ID
    """
    logger.info(f"Запрос блока {block_id} от пользователя {user.id}")

    # Получить язык команды пользователя
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        logger.error(f"Пользователь {user.id} не состоит ни в одной команде")
        return JSONResponse(
            content={"ok": False, "message": "User is not in any command"},
            status_code=400
        )

    blocks_dao = BlocksDAO(session)
    block = await blocks_dao.find_one_or_none_by_id(block_id)
    
    if not block:
        logger.error(f"Блок с ID {block_id} не найден")
        return JSONResponse(
            content={"ok": False, "message": "Block not found"},
            status_code=404
        )

    if block.language_id != command.language_id:
        logger.error(f"Язык блока {block.language_id} не совпадает с языком команды {command.language_id}")
        return JSONResponse(
            content={"ok": False, "message": "Language mismatch"},
            status_code=403
        )

    # Получаем загадки для блока
    riddles = await get_riddles_for_block(block_id, session)

    response_data = {
        "ok": True,
        "message": "Block loaded successfully",
        "block": {
            "id": block.id,
            "title": block.title,
            "language_id": block.language_id,
            "riddles": riddles
        }
    }

    return JSONResponse(content=response_data)

async def get_riddles_for_block(block_id: int, session: AsyncSession) -> list:
    """
    Получает список вопросов для указанного блока
    """
    questions_dao = QuestionsDAO(session)
    questions = await questions_dao.find_all(filters=FindQuestionsForBlock(block_id= block_id))
    
    result = []
    for question in questions:
        answers_dao = AnswersDAO(session)
        answers = await answers_dao.find_all(filters=FindAnswersForQuestion(question_id= question.id))
        
        result.append({
            "id": question.id,
            "title": question.title,
            "image_path": question.image_path,
            "geo_answered": question.geo_answered,
            "text_answered": question.text_answered,
            "image_path_answered": question.image_path_answered,
            "answers": [{
                "id": answer.id,
                "answer_text": answer.answer_text
            } for answer in answers]
        })
    
    return result
    