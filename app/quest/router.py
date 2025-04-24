from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dao import CommandsDAO, UsersDAO, EventsDAO
from app.auth.models import User, CommandsUser, Command
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit
from typing import Optional, Dict, Union

from app.quest.dao import BlocksDAO, QuestionsDAO, AnswersDAO, QuestionInsiderDAO, AttemptsDAO
from app.logger import logger
from app.quest.schemas import BlockFilter, FindAnswersForQuestion, FindQuestionsForBlock, FindInsidersForQuestion, MarkInsiderAttendanceRequest
from app.quest.models import Attempt, AttemptType, Question
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.quest.utils import compare_strings

router = APIRouter()

# --- Специфичные GET-маршруты (без path params в корне) --- 

@router.get("/")
async def get_all_quest_blocks(
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user),
    include_riddles: bool = False
):
    """Получает все блоки квеста"""
    # Проверяем авторизацию
    if not user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        
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

@router.get("/stats/commands")
async def get_commands_stats(
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """Получает статистику по всем командам и решенным ими загадкам"""
    logger.info("Начало получения статистики команд")
    # Проверяем авторизацию
    if not user:
        logger.warning("Пользователь не авторизован")
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        # Получаем все команды для текущего события
        commands_dao = CommandsDAO(session)
        event_dao = EventsDAO(session)
        curr_event_id = await event_dao.get_event_id_by_name()

        if not curr_event_id:
            logger.error("Не удалось получить информацию о текущем событии")
            return JSONResponse(
                content={"ok": False, "message": "Не удалось получить информацию о текущем событии"},
                status_code=500
            )

        # Получаем все команды текущего события
        commands = await commands_dao.find_all_by_event(
            curr_event_id,
            options=[
                selectinload(Command.users).joinedload(CommandsUser.user),
                selectinload(Command.users).joinedload(CommandsUser.role),
                selectinload(Command.language)
            ]
        )
        logger.info(f"Найдено команд: {len(commands)}")
        
        # Собираем статистику для каждой команды
        stats = []
        for command in commands:
            logger.info(f"Обработка команды: {command.name}")
            # Получаем статистику команды
            command_stats = await calculate_team_score_and_coins(command.id, session)
            
            # Получаем количество решенных загадок для команды
            solved_query = await session.execute(
                select(Attempt)
                .join(AttemptType)
                .where(Attempt.command_id == command.id)
                .where(Attempt.is_true == True)
                .where(AttemptType.name.in_(["question", "question_hint"]))
            )
            solved_riddles = solved_query.scalars().all()
            logger.info(f"Команда {command.name} решила загадок: {len(solved_riddles)}")
            
            # Получаем информацию об участниках команды
            participants = []
            for user_assoc in command.users:
                participants.append({
                    "id": user_assoc.user.id,
                    "name": user_assoc.user.full_name,
                    "role": user_assoc.role.name if user_assoc.role else "member"
                })

            logger.info(f"Собрана информация о команде {command.name}: участников - {len(participants)}, решено загадок - {len(solved_riddles)}, очки - {command_stats['score']}, монеты - {command_stats['coins']}")
            stats.append({
                "id": command.id,
                "name": command.name,
                "language": command.language.name if command.language else "default",
                "score": command_stats["score"],
                "coins": command_stats["coins"],
                "solved_riddles_count": len(solved_riddles),
                "participants_count": len(command.users),
                "participants": participants
            })
        
        # Сортируем команды по очкам (по убыванию)
        stats.sort(key=lambda x: x["score"], reverse=True)
        logger.info("Статистика команд успешно собрана и отсортирована")
        logger.info(stats)
        return JSONResponse(
            content={"ok": True, "stats": stats}
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики команд: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера"},
            status_code=500
        )

@router.get("/insider-tasks-status")
async def get_insider_tasks_status(
    command_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    scanner_user: Optional[User] = Depends(get_current_user)
):
    """
    Возвращает список загадок, назначенных текущему инсайдеру,
    и указывает, было ли уже отмечено посещение для указанной команды.
    """
    # Проверка авторизации и роли инсайдера
    if not scanner_user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    # Разрешаем доступ инсайдерам и организаторам
    if not scanner_user.role or scanner_user.role.name not in ["insider", "organizer"]:
        return JSONResponse(
            content={"ok": False, "message": "Доступ запрещен. Требуется роль инсайдера или организатора."},
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    logger.info(f"Инсайдер {scanner_user.id} запрашивает статус своих задач для команды {command_id}")
    
    # Заголовки для запрета кэширования
    cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    try:
        q_insider_dao = QuestionInsiderDAO(session)
        attempts_dao = AttemptsDAO(session)
        
        # Получаем все вопросы, назначенные этому инсайдеру
        assigned_questions = await q_insider_dao.find_questions_by_insider(scanner_user.id)
        
        if not assigned_questions:
            logger.info(f"Инсайдеру {scanner_user.id} не назначено ни одной загадки")
            return JSONResponse(content={"ok": True, "tasks": []}, headers=cache_headers)
        
        tasks_status = []
        for question in assigned_questions:
            # Проверяем, была ли уже успешная отметка (insider/insider_hint) для этой команды и вопроса
            is_marked = await attempts_dao.has_successful_insider_attempt(
                command_id=command_id,
                question_id=question.id
            )
            tasks_status.append({
                "id": question.id,
                "title": question.title,
                "is_attendance_marked": is_marked
            })
            
        logger.info(f"Статус задач для инсайдера {scanner_user.id} и команды {command_id} успешно получен")
        return JSONResponse(content={"ok": True, "tasks": tasks_status}, headers=cache_headers)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса задач инсайдера {scanner_user.id} для команды {command_id}: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера при получении статуса задач"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=cache_headers # Добавляем заголовки и в ответ с ошибкой
        )

# --- Маршруты с Path Parameters --- 

@router.get("/{block_id}")
async def get_quest_block(
    block_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """Получает конкретный блок квеста по его ID"""
    # Проверяем авторизацию
    if not user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        
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

@router.post("/check-answer/{riddle_id}")
async def check_answer(
    riddle_id: int,
    answer_data: dict,
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """
    Проверяет ответ пользователя на загадку
    """
    # Проверяем авторизацию
    if not user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        
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
    user: Optional[User] = Depends(get_current_user)
):
    """
    Возвращает подсказку для загадки
    """
    # Проверяем авторизацию
    if not user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        
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

@router.get("/riddle/{riddle_id}/insiders")
async def get_riddle_insiders(
    riddle_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """
    Получает список инсайдеров для указанной загадки.
    Доступно только организаторам.
    """
    # Проверяем авторизацию
    if not user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        
    # Проверяем роль пользователя (только организаторы могут получать информацию об инсайдерах)
    if not user.role or user.role.name != "organizer":
        return JSONResponse(
            content={"ok": False, "message": "Недостаточно прав для выполнения операции"},
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    try:
        logger.info(f"Запрос списка инсайдеров для загадки {riddle_id} от организатора {user.id}")
        
        # Проверяем существование загадки
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            return JSONResponse(
                content={"ok": False, "message": "Загадка не найдена"},
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Получаем всех инсайдеров для загадки
        insiders_dao = QuestionInsiderDAO(session)
        insiders = await insiders_dao.find_by_question_id(riddle_id)
        
        # Получаем полную информацию о пользователях-инсайдерах
        users_dao = UsersDAO(session)
        insiders_info = []
        
        for insider in insiders:
            insider_user = await users_dao.find_one_or_none_by_id(insider.user_id)
            if insider_user:
                insiders_info.append({
                    "id": insider_user.id,
                    "full_name": insider_user.full_name,
                    "telegram_username": insider_user.telegram_username
                })
        
        return JSONResponse(
            content={
                "ok": True,
                "riddle_id": riddle_id,
                "riddle_title": question.title,
                "insiders": insiders_info
            }
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка инсайдеров для загадки {riddle_id}: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- POST маршруты --- 

@router.post("/mark-insider-attendance")
async def mark_insider_attendance(
    request: MarkInsiderAttendanceRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    scanner_user: Optional[User] = Depends(get_current_user)
):
    """
    Отмечает посещение локации (загадки) инсайдером для указанной команды.
    Создает запись в таблице attempts с типом insider или insider_hint.
    """
    # Проверка авторизации и роли инсайдера
    if not scanner_user:
        return JSONResponse(
            content={"ok": False, "message": "Пользователь не авторизован"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    # Разрешаем доступ инсайдерам и организаторам
    if not scanner_user.role or scanner_user.role.name not in ["insider", "organizer"]:
        return JSONResponse(
            content={"ok": False, "message": "Доступ запрещен. Требуется роль инсайдера или организатора."},
            status_code=status.HTTP_403_FORBIDDEN
        )
        
    logger.info(f"Инсайдер {scanner_user.id} пытается отметить посещение вопроса {request.question_id} для команды {request.command_id} (сканированный пользователь {request.scanned_user_id})")
    
    try:
        q_insider_dao = QuestionInsiderDAO(session)
        attempts_dao = AttemptsDAO(session)
        
        # 1. Проверка, назначен ли вопрос инсайдеру
        is_assigned = await q_insider_dao.is_question_assigned_to_insider(
            question_id=request.question_id,
            insider_user_id=scanner_user.id
        )
        if not is_assigned:
            logger.warning(f"Вопрос {request.question_id} не назначен инсайдеру {scanner_user.id}")
            return JSONResponse(
                content={"ok": False, "message": "Этот вопрос не назначен вам."},
                status_code=status.HTTP_403_FORBIDDEN
            )
            
        # 2. Проверка на дубликат успешной инсайдерской отметки
        already_marked = await attempts_dao.has_successful_insider_attempt(
            command_id=request.command_id,
            question_id=request.question_id
        )
        if already_marked:
            logger.warning(f"Посещение вопроса {request.question_id} для команды {request.command_id} уже было отмечено")
            return JSONResponse(
                content={"ok": False, "message": "Посещение этого места для данной команды уже было отмечено."},
                status_code=status.HTTP_400_BAD_REQUEST # Используем 400, т.к. это ошибка запроса
            )
            
        # 3. Определение типа отметки (insider или insider_hint)
        has_hint_attempt = await attempts_dao.has_successful_attempt_of_type(
            command_id=request.command_id,
            question_id=request.question_id,
            attempt_type_name="question_hint"
        )
        
        attempt_type_name = "insider_hint" if has_hint_attempt else "insider"
        logger.info(f"Определен тип отметки: {attempt_type_name}")
        
        # 4. Получение ID типа попытки
        attempt_type_id = await attempts_dao.get_attempt_type_id_by_name(attempt_type_name)
        if not attempt_type_id:
            logger.error(f"Не удалось найти ID для типа попытки {attempt_type_name}")
            # Возможно, стоит вернуть 500, т.к. это проблема конфигурации БД
            return JSONResponse(
                content={"ok": False, "message": "Ошибка конфигурации сервера: тип попытки не найден."},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
        # 5. Создание записи Attempt
        new_attempt = Attempt(
            user_id=request.scanned_user_id, # ID сканированного пользователя
            command_id=request.command_id,
            question_id=request.question_id,
            attempt_type_id=attempt_type_id,
            is_true=True,
            attempt_text=f"Marked by insider {scanner_user.id}" # Опциональный текст для логов
        )
        session.add(new_attempt)
        await session.commit()
        
        logger.info(f"Посещение вопроса {request.question_id} для команды {request.command_id} успешно отмечено инсайдером {scanner_user.id} с типом {attempt_type_name}")
        
        return JSONResponse(content={"ok": True, "message": "Посещение успешно отмечено"})
        
    except Exception as e:
        logger.error(f"Ошибка при отметке посещения инсайдером {scanner_user.id} (вопрос {request.question_id}, команда {request.command_id}): {str(e)}", exc_info=True)
        await session.rollback() # Откатываем транзакцию в случае ошибки
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера при отметке посещения"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- Вспомогательные функции --- 

async def get_team_stats(user: Optional[User], session: AsyncSession) -> Optional[Dict]:
    """Общая функция для получения статистики команды"""
    if not user:
        logger.warning("Попытка получить статистику команды для неавторизованного пользователя")
        return None
        
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
