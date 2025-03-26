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
from app.quest.models import Attempt, AttemptType
from sqlalchemy import select

router = APIRouter()

async def get_team_stats(user: User, session: AsyncSession) -> dict:
    """Общая функция для получения статистики команды"""
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        logger.error(f"Пользователь {user.id} не состоит ни в одной команде")
        return None
    return await calculate_team_score_and_coins(command.id, session)

async def build_block_response(block, team_stats, include_riddles=False, session=None) -> dict:
    """Создание структуры ответа для блока"""
    response = {
        "id": block.id,
        "title": block.title,
        "language_id": block.language_id
    }
    if include_riddles:
        response['riddles'] = await get_riddles_for_block(block.id, session)
    return response

@router.get("/")
async def get_all_quest_blocks(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user),
    include_riddles: bool = False
):
    """Получает все блоки квеста"""
    team_stats = await get_team_stats(user, session)
    if not team_stats:
        return JSONResponse(
            content={"ok": False, "message": "User is not in any command"},
            status_code=400
        )

    blocks_dao = BlocksDAO(session)
    command = await UsersDAO(session).find_user_command_in_event(user.id)
    blocks = await blocks_dao.find_all(filters=BlockFilter(language_id=command.language_id))

    response_data = {
        "ok": True,
        "message": "Blocks load successful",
        "team_score": team_stats["score"],
        "team_coins": team_stats["coins"],
        "blocks": [await build_block_response(block, team_stats, include_riddles, session) for block in blocks]
    }

    return JSONResponse(content=response_data)

@router.get("/{block_id}")
async def get_quest_block(
    block_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Получает конкретный блок квеста по его ID"""
    team_stats = await get_team_stats(user, session)
    if not team_stats:
        return JSONResponse(
            content={"ok": False, "message": "User is not in any command"},
            status_code=400
        )

    blocks_dao = BlocksDAO(session)
    block = await blocks_dao.find_one_or_none_by_id(block_id)
    
    if not block:
        return JSONResponse(
            content={"ok": False, "message": "Block not found"},
            status_code=404
        )

    command = await UsersDAO(session).find_user_command_in_event(user.id)
    if block.language_id != command.language_id:
        return JSONResponse(
            content={"ok": False, "message": "Language mismatch"},
            status_code=403
        )

    response_data = {
        "ok": True,
        "message": "Block loaded successfully",
        "team_score": team_stats["score"],
        "team_coins": team_stats["coins"],
        "block": await build_block_response(block, team_stats, True, session)
    }

    return JSONResponse(content=response_data)

async def get_riddle_data(question, solved: bool) -> dict:
    """Формирует данные загадки в зависимости от того, решена она или нет"""
    if solved:
        return {
            "id": question.id,
            "title": question.title,
            "text_answered": question.text_answered,
            "image_path_answered": question.image_path_answered,
            "geo_answered": question.geo_answered
        }
    return {
        "id": question.id,
        "image_path": question.image_path
    }

async def get_riddles_for_block(block_id: int, session: AsyncSession) -> list:
    """
    Получает список вопросов для указанного блока
    """
    questions_dao = QuestionsDAO(session)
    questions = await questions_dao.find_all(filters=FindQuestionsForBlock(block_id=block_id))
    
    result = []
    for question in questions:
        solved_attempt = await session.execute(
            select(Attempt)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
        )
        solved = solved_attempt.scalar_one_or_none() is not None
        result.append(await get_riddle_data(question, solved))
    
    return result

@router.post("/check-answer/{riddle_id}")
async def check_answer(
    riddle_id: int,
    answer_data: dict,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """
    Проверяет ответ пользователя на загадку
    """
    try:
        logger.info(f"Начало проверки ответа. Пользователь: {user.id}, Загадка: {riddle_id}")
        
        # Получаем загадку и проверяем команду
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            return JSONResponse(
                content={"ok": False, "message": "Riddle not found"},
                status_code=404
            )
        
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user.id)
        if not command:
            return JSONResponse(
                content={"ok": False, "message": "User is not in any command"},
                status_code=400
            )

        # Проверяем существующую попытку
        existing_attempt = await session.execute(
            select(Attempt)
            .where(Attempt.command_id == command.id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
        )
        if existing_attempt.scalar_one_or_none():
            return JSONResponse(
                content={"ok": False, "message": "Reward already given for this riddle"},
                status_code=400
            )
        
        # Проверяем ответ
        def normalize_text(text: str) -> str:
            return ''.join(c for c in text.lower() if c.isalnum())

        user_answer = normalize_text(answer_data.get('answer', ''))
        answers_dao = AnswersDAO(session)
        answers = await answers_dao.find_all(filters=FindAnswersForQuestion(question_id=riddle_id))
        is_correct = any(user_answer == normalize_text(answer.answer_text) for answer in answers)
        
        # Создаем попытку
        attempt_type = await session.execute(
            select(AttemptType).where(AttemptType.name == "question")
        )
        attempt_type = attempt_type.scalar_one_or_none()
        if not attempt_type:
            return JSONResponse(
                content={"ok": False, "message": "Attempt type not found"},
                status_code=404
            )

        attempt = Attempt(
            user_id=user.id,
            command_id=command.id,
            question_id=question.id,
            attempt_type_id=attempt_type.id,
            attempt_text=answer_data.get('answer', ''),
            is_true=is_correct
        )
        session.add(attempt)
        await session.commit()

        # Формируем ответ
        team_stats = await calculate_team_score_and_coins(command.id, session)
        return JSONResponse(content={
            "ok": True,
            "isCorrect": is_correct,
            "updatedRiddle": await get_riddle_data(question, is_correct) if is_correct else None,
            "team_score": team_stats["score"],
            "team_coins": team_stats["coins"]
        })
        
    except Exception as e:
        logger.error(f"Ошибка при проверке ответа. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Internal server error"},
            status_code=500
        )

async def calculate_team_score_and_coins(command_id: int, session: AsyncSession) -> dict:
    """
    Вычисляет счёт и количество монет команды на основе попыток
    """
    # Получаем все успешные попытки команды
    result = await session.execute(
        select(AttemptType.score, AttemptType.money)
        .join(Attempt, Attempt.attempt_type_id == AttemptType.id)
        .where(Attempt.command_id == command_id)
        .where(Attempt.is_true == True)
    )
    scores_and_coins = result.all()
    
    # Суммируем все баллы и монеты
    total_score = sum(score for score, _ in scores_and_coins) if scores_and_coins else 0
    total_coins = sum(coins for _, coins in scores_and_coins) if scores_and_coins else 0
    
    return {
        "score": total_score,
        "coins": total_coins
    }
