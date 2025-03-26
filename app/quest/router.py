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

    # Вычисляем счёт и монеты команды
    team_stats = await calculate_team_score_and_coins(command.id, session)

    # Пример данных блоков
    blocks_dao = BlocksDAO(session)

    # TODO: По-хорошему это надо закэшировать
    blocks = await blocks_dao.find_all(filters=BlockFilter(language_id=command.language_id))

    response_data = {
        "ok": True,
        "message": "Blocks load successful",
        "team_score": team_stats["score"],  # Добавляем счёт команды
        "team_coins": team_stats["coins"],  # Добавляем монеты команды
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

    # Вычисляем счёт и монеты команды
    team_stats = await calculate_team_score_and_coins(command.id, session)

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
        "team_score": team_stats["score"],  # Добавляем счёт команды
        "team_coins": team_stats["coins"],  # Добавляем монеты команды
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
    questions = await questions_dao.find_all(filters=FindQuestionsForBlock(block_id=block_id))
    
    result = []
    for question in questions:
        # Проверяем, была ли загадка решена командой
        solved_attempt = await session.execute(
            select(Attempt)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
        )
        solved_attempt = solved_attempt.scalar_one_or_none()
        
        # Если загадка решена, добавляем дополнительные данные
        if solved_attempt:
            result.append({
                "id": question.id,
                "title": question.title,
                "text_answered": question.text_answered,
                "image_path_answered": question.image_path_answered,
                "geo_answered": question.geo_answered
            })
        else:
            result.append({
                "id": question.id,
                "image_path": question.image_path
            })
    
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
        logger.info(f"Начало проверки ответа. Пользователь: {user.id} (username: {user.telegram_username}), Загадка: {riddle_id}")
        logger.debug(f"Полученные данные ответа: {answer_data}")
        
        # Получаем загадку
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        
        if not question:
            logger.warning(f"Загадка не найдена. ID: {riddle_id}, Пользователь: {user.id}")
            return JSONResponse(
                content={"ok": False, "message": "Riddle not found"},
                status_code=404
            )
        
        logger.debug(f"Найдена загадка: ID={question.id}, Название='{question.title}'")
        
        # Получаем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user.id)
        if not command:
            logger.error(f"Пользователь {user.id} не состоит ни в одной команде")
            return JSONResponse(
                content={"ok": False, "message": "User is not in any command"},
                status_code=400
            )

        # Проверяем, было ли уже начисление за эту загадку
        existing_attempt = await session.execute(
            select(Attempt)
            .where(Attempt.command_id == command.id)
            .where(Attempt.question_id == question.id)
            .where(Attempt.is_true == True)
        )
        existing_attempt = existing_attempt.scalar_one_or_none()
        
        if existing_attempt:
            logger.warning(f"Начисление уже было произведено. Команда: {command.id}, Загадка: {question.id}")
            return JSONResponse(
                content={"ok": False, "message": "Reward already given for this riddle"},
                status_code=400
            )
        
        # Получаем все возможные ответы
        answers_dao = AnswersDAO(session)
        answers = await answers_dao.find_all(filters=FindAnswersForQuestion(question_id=riddle_id))
        logger.debug(f"Найдено {len(answers)} вариантов ответа для загадки {riddle_id}")
        
        # Проверяем ответ
        def normalize_text(text: str) -> str:
            """Нормализует текст для сравнения: удаляет лишние пробелы, приводит к нижнему регистру"""
            # Удаляем все не буквенно-цифровые символы и пробелы
            return ''.join(c for c in text.lower() if c.isalnum())

        user_answer = normalize_text(answer_data.get('answer', ''))
        logger.debug(f"Нормализованный ответ пользователя: '{user_answer}'")
        
        for answer in answers:
            normalized_answer = normalize_text(answer.answer_text)
            logger.debug(f"Нормализованный вариант ответа: '{normalized_answer}'")
            
        is_correct = any(user_answer == normalize_text(answer.answer_text) for answer in answers)
        logger.info(f"Результат проверки ответа: {'Правильно' if is_correct else 'Неправильно'}. Пользователь: {user.id}, Загадка: {riddle_id}")

        attempt_type_name = "question"
        attempt_type = await session.execute(
            select(AttemptType)
            .where(AttemptType.name == attempt_type_name)
        )
        attempt_type = attempt_type.scalar_one_or_none()
        
        if not attempt_type:
            logger.error(f"Тип попытки '{attempt_type_name}' не найден")
            return JSONResponse(
                content={"ok": False, "message": "Attempt type not found"},
                status_code=404
            )

        # Создаем попытку
        attempt = Attempt(
            user_id=user.id,
            command_id=command.id,
            question_id=question.id,
            attempt_type_id=attempt_type.id,
            attempt_text=answer_data.get('answer', ''),  # Сохраняем оригинальный ответ
            is_true=is_correct
        )
        session.add(attempt)
        await session.commit()

        if is_correct:
            # Формируем обновлённые данные загадки только при правильном ответе
            updated_riddle = {
                "id": question.id,
                "title": question.title,
                "text_answered": question.text_answered,
                "image_path_answered": question.image_path_answered,
                "geo_answered": question.geo_answered
            }
        else:
            updated_riddle = None
            
        # Получаем обновлённые счёт и монеты команды
        team_stats = await calculate_team_score_and_coins(command.id, session)
        
        logger.debug(f"Возвращаемые данные загадки: {updated_riddle}")
        return JSONResponse(content={
            "ok": True,
            "isCorrect": is_correct,
            "updatedRiddle": updated_riddle,  # Будет null при неправильном ответе
            "team_score": team_stats["score"],  # Добавляем счёт команды
            "team_coins": team_stats["coins"]   # Добавляем монеты команды
        })
        
    except Exception as e:
        logger.error(f"Критическая ошибка при проверке ответа. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
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
