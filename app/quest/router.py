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
from app.quest.models import Attempt, AttemptType, Question
from sqlalchemy import select

from app.quest.utils import compare_strings

router = APIRouter()

async def get_team_stats(user: User, session: AsyncSession) -> dict:
    """Общая функция для получения статистики команды"""
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        logger.error(f"Пользователь {user.id} не состоит ни в одной команде")
        return None
    stats = await calculate_team_score_and_coins(command.id, session)
    stats['user_id'] = user.id  # Добавляем ID пользователя
    return stats

async def get_solved_riddles_count(block_id: int, command_id: int, session: AsyncSession) -> int:
    """Получает количество решённых загадок в блоке для команды, учитывая только попытки типа question или question_hint"""
    result = await session.execute(
        select(Attempt)
        .join(Question, Question.id == Attempt.question_id)
        .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
        .where(Question.block_id == block_id)
        .where(Attempt.command_id == command_id)
        .where(Attempt.is_true == True)
        .where(AttemptType.name.in_(["question", "question_hint"]))
    )
    return len(result.scalars().all())

async def get_total_riddles_count(block_id: int, session: AsyncSession) -> int:
    """Получает общее количество загадок в блоке"""
    result = await session.execute(
        select(Question)
        .where(Question.block_id == block_id)
    )
    return len(result.scalars().all())

async def get_insider_riddles_count(block_id: int, command_id: int, session: AsyncSession) -> int:
    """Получает количество загадок, на которые приехали (insider или insider_hint)"""
    result = await session.execute(
        select(Attempt)
        .join(Question, Question.id == Attempt.question_id)
        .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
        .where(Question.block_id == block_id)
        .where(Attempt.command_id == command_id)
        .where(Attempt.is_true == True)
        .where(AttemptType.name.in_(["insider", "insider_hint"]))
    )
    return len(result.scalars().all())

async def build_block_response(block, team_stats, command, include_riddles=False, session=None) -> dict:
    """Создание структуры ответа для блока"""
    response = {
        "id": block.id,
        "title": block.title,
        "language_id": block.language_id
    }
    if include_riddles:
        response['riddles'] = await get_riddles_for_block(block.id, session, command.id)
    else:
        # Используем переданную команду
        solved = await get_solved_riddles_count(block.id, command.id, session)
        total = await get_total_riddles_count(block.id, session)
        insider = await get_insider_riddles_count(block.id, command.id, session)
        response['solved_count'] = solved
        response['total_count'] = total
        response['insider_count'] = insider
        response['progress'] = round((solved / total) * 100) if total > 0 else 0
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

    # Получаем команду один раз
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        return JSONResponse(
            content={"ok": False, "message": "User is not in any command"},
            status_code=400
        )

    blocks_dao = BlocksDAO(session)
    blocks = await blocks_dao.find_all(filters=BlockFilter(language_id=command.language_id))

    response_data = {
        "ok": True,
        "message": "Blocks load successful",
        "team_score": team_stats["score"],
        "team_coins": team_stats["coins"],
        "blocks": [await build_block_response(block, team_stats, command, include_riddles, session) for block in blocks]
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
        "block": await build_block_response(block, team_stats, command, True, session)
    }

    return JSONResponse(content=response_data)

async def get_riddle_data(question, solved: bool, session: AsyncSession, command_id: int) -> dict:
    """Формирует данные загадки с учётом insider-попыток"""
    if solved:
        # Проверяем наличие успешных insider-попыток только для решённых загадок
        insider_attempt = await session.execute(
            select(Attempt)
            .join(AttemptType)
            .where(Attempt.command_id == command_id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
            .where(AttemptType.name.in_(["insider", "insider_hint"]))
        )
        has_insider_attempt = insider_attempt.scalar_one_or_none() is not None

        # Проверяем, запрашивал ли команда подсказку для этой загадки
        hint_attempt = await session.execute(
            select(Attempt)
            .join(AttemptType)
            .where(Attempt.command_id == command_id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
            .where(AttemptType.name == "hint")
        )
        has_hint = hint_attempt.scalar_one_or_none() is not None

        return {
            "id": question.id,
            "title": question.title,
            "text_answered": question.text_answered,
            "image_path_answered": question.image_path_answered,
            "geo_answered": question.geo_answered,
            "has_insider_attempt": has_insider_attempt,
            "has_hint": has_hint and question.hint_path is not None,
            "hint": question.hint_path if has_hint else None
        }
    
    # Если загадка не решена, проверяем, доступна ли подсказка
    hint_attempt = await session.execute(
        select(Attempt)
        .join(AttemptType)
        .where(Attempt.command_id == command_id)
        .where(Attempt.question_id == question.id)
        .where(Attempt.is_true == True)
        .where(AttemptType.name == "hint")
    )
    has_hint = hint_attempt.scalar_one_or_none() is not None
    
    return {
        "id": question.id,
        "title": question.title,
        "image_path": question.image_path,
        "has_hint": has_hint and question.hint_path is not None,
        "hint": question.hint_path if has_hint else None
    }

async def get_riddles_for_block(block_id: int, session: AsyncSession, command_id: int) -> list:
    """
    Получает список вопросов для указанного блока с учётом insider-попыток
    """
    questions_dao = QuestionsDAO(session)
    questions = await questions_dao.find_all(filters=FindQuestionsForBlock(block_id=block_id))
    
    result = []
    for question in questions:
        # Проверяем наличие успешной попытки с ответом типа "question"
        solved_attempt = await session.execute(
            select(Attempt)
            .join(AttemptType)
            .where(Attempt.question_id == question.id)
            .where(Attempt.command_id == command_id)
            .where(Attempt.is_true == True)
            .where(AttemptType.name.in_(["question", "question_hint"]))
        )
        solved = solved_attempt.scalar() is not None
        result.append(await get_riddle_data(question, solved, session, command_id))
    
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
            .join(AttemptType)
            .where(Attempt.command_id == command.id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
            .where(AttemptType.name.in_(["question", "question_hint"]))
        )
        if existing_attempt.scalar_one_or_none():
            return JSONResponse(
                content={"ok": False, "message": "Reward already given for this riddle"},
                status_code=400
            )
        
        
        user_answer = answer_data.get('answer', '')
        answers_dao = AnswersDAO(session)
        answers = await answers_dao.find_all(filters=FindAnswersForQuestion(question_id=riddle_id))
        is_correct = any(compare_strings(user_answer, answer.answer_text) for answer in answers)
        
        # Создаем попытку
        # Проверяем наличие успешной попытки с подсказкой
        hint_attempt = await session.execute(
            select(Attempt)
            .join(AttemptType)
            .where(Attempt.command_id == command.id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
            .where(AttemptType.name == "hint")
        )
        has_hint = hint_attempt.scalar_one_or_none() is not None

        # Определяем тип попытки в зависимости от наличия подсказки
        attempt_type_name = "question_hint" if has_hint else "question"
        attempt_type = await session.execute(
            select(AttemptType).where(AttemptType.name == attempt_type_name)
        )
        attempt_type = attempt_type.scalar_one_or_none()
        if not attempt_type:
            return JSONResponse(
                content={"ok": False, "message": "Attempt type not found"},
                status_code=404
            )
        #TODO is_correct в случае если хватает монеток
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
            "updatedRiddle": await get_riddle_data(question, is_correct, session, command.id) if is_correct else None,
            "team_score": team_stats["score"],
            "team_coins": team_stats["coins"]
        })
        
    except Exception as e:
        logger.error(f"Ошибка при проверке ответа. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Internal server error"},
            status_code=500
        )

@router.get("/hint/{riddle_id}")
async def get_hint(
    riddle_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """
    Получает подсказку для загадки, учитывая баллы и монеты команды
    """
    try:
        logger.info(f"Запрос подсказки. Пользователь: {user.id}, Загадка: {riddle_id}")
        
        # Получаем тип попытки для подсказки
        attempt_type = await session.execute(
            select(AttemptType).where(AttemptType.name == "hint")
        )
        attempt_type = attempt_type.scalar_one_or_none()
        if not attempt_type:
            return JSONResponse(
                content={"ok": False, "message": "Тип попытки для подсказки не найден"},
                status_code=404
            )
        
        # Получаем загадку
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            return JSONResponse(
                content={"ok": False, "message": "Загадка не найдена"},
                status_code=404
            )
        
        # Проверяем наличие подсказки
        if not question.hint_path:
            return JSONResponse(
                content={"ok": False, "message": "Подсказка недоступна для этой загадки"},
                status_code=404
            )
        
        # Проверяем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user.id)
        if not command:
            return JSONResponse(
                content={"ok": False, "message": "Пользователь не состоит ни в одной команде"},
                status_code=400
            )
        
        # Проверяем, запрашивал ли уже кто-то из команды подсказку для этой загадки
        existing_hint_attempt = await session.execute(
            select(Attempt)
            .join(AttemptType)
            .where(Attempt.command_id == command.id)
            .where(Attempt.question_id == question.id)
            .where(AttemptType.name == "hint")
        )
        
        # Если уже запрашивали подсказку, возвращаем её без создания новой попытки
        if existing_hint_attempt.scalar_one_or_none():
            team_stats = await calculate_team_score_and_coins(command.id, session)
            return JSONResponse(content={
                "ok": True,
                "hint": question.hint_path,
                "team_score": team_stats["score"],
                "team_coins": team_stats["coins"]
            })
            
        # Проверяем баланс команды
        team_stats = await calculate_team_score_and_coins(command.id, session)
        if team_stats["coins"] < abs(attempt_type.money):
            return JSONResponse(
                content={"ok": False, "message": "Недостаточно монет для получения подсказки"},
                status_code=400
            )
        
        # Создаем попытку запроса подсказки
        attempt = Attempt(
            user_id=user.id,
            command_id=command.id,
            question_id=question.id,
            attempt_type_id=attempt_type.id,
            attempt_text="hint_request",
            is_true=True  # Всегда успешная попытка
        )
        session.add(attempt)
        await session.commit()
        
        # Обновляем и возвращаем статистику команда
        team_stats = await calculate_team_score_and_coins(command.id, session)
        return JSONResponse(content={
            "ok": True,
            "hint": question.hint_path,
            "team_score": team_stats["score"],
            "team_coins": team_stats["coins"]
        })
        
    except Exception as e:
        logger.error(f"Ошибка при запросе подсказки. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера"},
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
