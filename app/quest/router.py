from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dao import CommandsDAO, EventsDAO, UsersDAO
from app.auth.models import Command, CommandsUser, Language, User
from app.dependencies.auth_dep import get_current_event_name, require_role
from app.dependencies.dao_dep import get_session_with_commit
from app.dependencies.quest_dep import get_authenticated_user_and_command
# Import exceptions
from app.exceptions import (AttemptTypeNotFoundException,
                            AttendanceAlreadyMarkedException,
                            BlockNotFoundException,
                            CannotMarkUnsolvedException,
                            EventNotFoundException, HintUnavailableException,
                            InsufficientCoinsException,
                            InternalServerErrorException,
                            LanguageMismatchException,
                            QuestionNotAssignedException,
                            RewardAlreadyGivenException,
                            RiddleNotFoundException)
from app.logger import logger
from app.quest.dao import (AnswersDAO, AttemptsDAO, BlocksDAO,
                           QuestionInsiderDAO, QuestionsDAO)
from app.quest.models import Attempt, Block
from app.quest.schemas import (AnswerRequest, BlockFilter, BlockStructureInfo,
                               CheckAnswerResponse,
                               EventQuestStructureResponse,
                               FindAnswersForQuestion, GetAllBlocksResponse,
                               GetBlockResponse, GetCommandsStatsResponse,
                               GetInsiderTasksResponse, HintResponse,
                               MarkAttendanceResponse,
                               MarkInsiderAttendanceRequest,
                               QuestionStructureInfo, RiddleInsidersResponse)
from app.quest.utils import (build_block_response, compare_strings,
                             get_riddle_data)

router = APIRouter()

# --- Специфичные GET-маршруты (без path params в корне) --- 

@router.get("/", response_model=GetAllBlocksResponse)
async def get_all_quest_blocks(
    session: AsyncSession = Depends(get_session_with_commit),
    auth_data: Tuple[User, Command] = Depends(get_authenticated_user_and_command),
    include_riddles: bool = False
):
    """Получает все блоки квеста"""
    user, command = auth_data
        
    attempts_dao = AttemptsDAO(session)
    team_stats = await attempts_dao.calculate_team_score_and_coins(command.id)

    blocks_dao = BlocksDAO(session)
    blocks = await blocks_dao.find_all(filters=BlockFilter(language_id=command.language_id))

    block_responses = [await build_block_response(block, command, include_riddles, session) for block in blocks]

    return GetAllBlocksResponse(
        ok=True,
        message="Blocks load successful",
        team_score=team_stats["score"],
        team_coins=team_stats["coins"],
        blocks=block_responses
    )

@router.get("/commands/stats", response_model=GetCommandsStatsResponse)
async def get_commands_stats(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(require_role(["organizer"])),
    event_name: str = Depends(get_current_event_name)
):
    """Получает статистику по всем командам и решенным ими загадкам"""
    logger.info("Начало получения статистики команд")

    try:
        commands_dao = CommandsDAO(session)
        event_dao = EventsDAO(session)
        curr_event_id = await event_dao.get_event_id_by_name(event_name)

        if not curr_event_id:
            logger.error("Не удалось получить информацию о текущем событии")
            raise EventNotFoundException

        commands = await commands_dao.find_all_by_event(
            curr_event_id,
            options=[
                selectinload(Command.users).joinedload(CommandsUser.user),
                selectinload(Command.users).joinedload(CommandsUser.role),
                selectinload(Command.language)
            ]
        )
        logger.info(f"Найдено команд: {len(commands)}")

        stats = []
        attempts_dao = AttemptsDAO(session)
        for command in commands:
            logger.info(f"Обработка команды: {command.name}")
            command_stats = await attempts_dao.calculate_team_score_and_coins(command.id)
            
            solved_riddles_count = await attempts_dao.get_solved_riddles_count_for_command(command.id)
            logger.info(f"Команда {command.name} решила загадок: {solved_riddles_count}")

            participants = [
                {
                    "id": user_assoc.user.id,
                    "name": user_assoc.user.full_name,
                    "role": user_assoc.role.name if user_assoc.role else "member"
                }
                for user_assoc in command.users
            ]

            logger.info(f"Собрана информация о команде {command.name}: участников - {len(participants)}, решено загадок - {solved_riddles_count}, очки - {command_stats['score']}, монеты - {command_stats['coins']}")
            stats.append({
                "id": command.id,
                "name": command.name,
                "language": command.language.name if command.language else "default",
                "score": command_stats["score"],
                "coins": command_stats["coins"],
                "solved_riddles_count": solved_riddles_count,
                "participants_count": len(command.users),
                "participants": participants
            })
        
        stats.sort(key=lambda x: x["score"], reverse=True)
        logger.info("Статистика команд успешно собрана и отсортирована")
        
        return GetCommandsStatsResponse(ok=True, stats=stats)
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Ошибка при получении статистики команд: {str(e)}", exc_info=True)
        raise InternalServerErrorException

@router.get("/insiders/tasks/status", response_model=GetInsiderTasksResponse)
async def get_insider_tasks_status(
    command_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    scanner_user: User = Depends(require_role(["insider", "organizer", "ctc"]))
):
    """
    Возвращает список загадок, назначенных текущему инсайдеру,
    и указывает, было ли уже отмечено посещение для указанной команды.
    (Оптимизированная версия)
    """
    logger.info(f"Инсайдер {scanner_user.id} запрашивает статус своих задач для команды {command_id} (оптимизированный)")
    
    try:
        commands_dao = CommandsDAO(session)
        command = await commands_dao.find_one_or_none_by_id(command_id)
        if not command:
            logger.warning(f"Команда с ID {command_id} не найдена при запросе статуса задач инсайдером {scanner_user.id}")
            return GetInsiderTasksResponse(ok=True, tasks=[])
        if not command.language_id:
            logger.error(f"У команды {command_id} не установлен язык.")
            raise InternalServerErrorException(detail="Command language is not set.")
        command_language_id = command.language_id

        q_insider_dao = QuestionInsiderDAO(session)
        attempts_dao = AttemptsDAO(session)
        
        assigned_questions = await q_insider_dao.find_questions_by_insider(scanner_user.id)
        
        # --- Добавлено: Фильтрация по языку команды ---
        filtered_questions = [
            q for q in assigned_questions 
            if q.block.language_id == command_language_id
        ]
        # --- Конец добавленного ---

        if not filtered_questions: # --- Изменено: проверка отфильтрованного списка ---
            logger.info(f"Инсайдеру {scanner_user.id} не назначено ни одной загадки на языке команды {command_id}")
            return GetInsiderTasksResponse(ok=True, tasks=[])
        
        # --- Изменено: использование отфильтрованного списка ---
        assigned_question_ids = [q.id for q in filtered_questions]

        attempt_statuses = await attempts_dao.get_attempts_status_for_block(command_id, assigned_question_ids)
        solved_ids = attempt_statuses.get("solved", set())
        insider_visited_ids = attempt_statuses.get("insider_visited", set())

        tasks_status = []
        # --- Изменено: итерация по отфильтрованному списку ---
        for question in filtered_questions:
            is_attendance_marked = question.id in insider_visited_ids
            is_solved_by_team = question.id in solved_ids

            tasks_status.append({
                "id": question.id,
                "title": question.title,
                "is_attendance_marked": is_attendance_marked,
                "can_mark_attendance": is_solved_by_team and not is_attendance_marked
            })
            
        logger.info(f"Статус задач для инсайдера {scanner_user.id} и команды {command_id} успешно получен (оптимизированный)")
        return GetInsiderTasksResponse(ok=True, tasks=tasks_status)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса задач инсайдера {scanner_user.id} для команды {command_id}: {str(e)}", exc_info=True)
        raise InternalServerErrorException

# --- Маршруты с Path Parameters --- 

@router.get("/{block_id}", response_model=GetBlockResponse)
async def get_quest_block(
    block_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    auth_data: Tuple[User, Command] = Depends(get_authenticated_user_and_command)
):
    """Получает конкретный блок квеста по его ID"""
    user, command = auth_data

    attempts_dao = AttemptsDAO(session)
    team_stats = await attempts_dao.calculate_team_score_and_coins(command.id)

    blocks_dao = BlocksDAO(session)
    block = await blocks_dao.find_one_or_none_by_id(block_id)
    
    if not block:
        raise BlockNotFoundException

    if block.language_id != command.language_id:
        raise LanguageMismatchException

    block_response = await build_block_response(block, command, True, session)

    return GetBlockResponse(
        ok=True,
        message="Block loaded successfully",
        team_score=team_stats["score"],
        team_coins=team_stats["coins"],
        block=block_response
    )

@router.post("/riddles/{riddle_id}/check-answer", response_model=CheckAnswerResponse)
async def check_answer(
    riddle_id: int,
    answer_data: AnswerRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    auth_data: Tuple[User, Command] = Depends(get_authenticated_user_and_command)
):
    """
    Проверяет ответ пользователя на загадку
    """
    user, command = auth_data
    try:
        logger.info(f"Начало проверки ответа. Пользователь: {user.id}, Загадка: {riddle_id}")
        
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            raise RiddleNotFoundException
        
        attempts_dao = AttemptsDAO(session)

        if await attempts_dao.has_successful_solve_attempt(command.id, question.id):
             raise RewardAlreadyGivenException
        
        user_answer = answer_data.answer
        answers_dao = AnswersDAO(session)
        answers = await answers_dao.find_all(filters=FindAnswersForQuestion(question_id=riddle_id))
        is_correct = any(compare_strings(user_answer, answer.answer_text) for answer in answers)
        
        has_hint = await attempts_dao.has_successful_attempt_of_type(command.id, question.id, "hint")
        attempt_type_name = "question_hint" if has_hint else "question"
        
        attempt_type = await attempts_dao.get_attempt_type_by_name(attempt_type_name)
        if not attempt_type:
            logger.error(f"Attempt type '{attempt_type_name}' not found in DB.")
            raise AttemptTypeNotFoundException

        attempt = Attempt(
            user_id=user.id,
            command_id=command.id,
            question_id=question.id,
            attempt_type_id=attempt_type.id,
            attempt_text=user_answer,
            is_true=is_correct
        )
        session.add(attempt)
        await session.commit()

        team_stats = await attempts_dao.calculate_team_score_and_coins(command.id)

        updated_riddle_data = None
        if is_correct:
            question = await questions_dao.find_one_or_none_by_id(riddle_id)
            if not question:
                logger.error(f"Question {riddle_id} disappeared after commit in check_answer for command {command.id}")
            else: 
                attempt_statuses = await attempts_dao.get_attempts_status_for_block(command.id, [question.id])
                updated_riddle_data = await get_riddle_data(question, attempt_statuses, session)

        return CheckAnswerResponse(
            ok=True,
            isCorrect=is_correct,
            updatedRiddle=updated_riddle_data, 
            team_score=team_stats["score"],
            team_coins=team_stats["coins"]
        )
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Ошибка при проверке ответа. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
        await session.rollback()
        raise InternalServerErrorException

@router.get("/riddles/{riddle_id}/hint", response_model=HintResponse)
async def get_hint(
    riddle_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    auth_data: Tuple[User, Command] = Depends(get_authenticated_user_and_command)
):
    """
    Возвращает подсказку для загадки
    """
    user, command = auth_data
    try:
        logger.info(f"Запрос подсказки. Пользователь: {user.id}, Загадка: {riddle_id}")
        
        attempts_dao = AttemptsDAO(session)

        attempt_type = await attempts_dao.get_attempt_type_by_name("hint")
        if not attempt_type:
            logger.error("Не найден тип попытки 'hint'.")
            raise AttemptTypeNotFoundException
        
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            raise RiddleNotFoundException
        if not question.hint_path:
             raise HintUnavailableException

        existing_hint_attempt = await attempts_dao.has_successful_attempt_of_type(command.id, question.id, "hint")        
        team_stats = await attempts_dao.calculate_team_score_and_coins(command.id)

        if existing_hint_attempt:
            return HintResponse(
                ok=True,
                hint=question.hint_path,
                team_score=team_stats["score"],
                team_coins=team_stats["coins"]
            )

        if team_stats["coins"] < abs(attempt_type.money):
            raise InsufficientCoinsException

        attempt = Attempt(
            user_id=user.id,
            command_id=command.id,
            question_id=question.id,
            attempt_type_id=attempt_type.id,
            attempt_text="hint_request",
            is_true=True
        )
        session.add(attempt)
        await session.commit()

        team_stats_updated = await attempts_dao.calculate_team_score_and_coins(command.id)
        return HintResponse(
            ok=True,
            hint=question.hint_path,
            team_score=team_stats_updated["score"],
            team_coins=team_stats_updated["coins"]
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Ошибка при запросе подсказки. Пользователь: {user.id}, Загадка: {riddle_id}, Ошибка: {str(e)}", exc_info=True)
        await session.rollback()
        raise InternalServerErrorException

@router.get("/riddles/{riddle_id}/insiders", response_model=RiddleInsidersResponse)
async def get_riddle_insiders(
    riddle_id: int,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(require_role(["organizer"]))
):
    """
    Получает список инсайдеров для указанной загадки.
    Доступно только организаторам.
    """
    try:
        logger.info(f"Запрос списка инсайдеров для загадки {riddle_id} от организатора {user.id}")
        
        questions_dao = QuestionsDAO(session)
        question = await questions_dao.find_one_or_none_by_id(riddle_id)
        if not question:
            raise RiddleNotFoundException
        
        insiders_dao = QuestionInsiderDAO(session)
        insiders = await insiders_dao.find_by_question_id(riddle_id)
        
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
        
        return RiddleInsidersResponse(
            ok=True,
            riddle_id=riddle_id,
            riddle_title=question.title,
            insiders=insiders_info
        )
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Ошибка при получении списка инсайдеров для загадки {riddle_id}: {str(e)}", exc_info=True)
        raise InternalServerErrorException

# --- POST маршруты --- 

@router.post("/insiders/attendance/mark", response_model=MarkAttendanceResponse)
async def mark_insider_attendance(
    request: MarkInsiderAttendanceRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    scanner_user: User = Depends(require_role(["insider", "organizer", "ctc"]))
):
    """
    Отмечает посещение локации (загадки) инсайдером для указанной команды.
    Создает запись в таблице attempts с типом insider или insider_hint.
    """
    logger.info(f"Инсайдер {scanner_user.id} пытается отметить посещение вопроса {request.question_id} для команды {request.command_id} (сканированный пользователь {request.scanned_user_id})")
    
    try:
        q_insider_dao = QuestionInsiderDAO(session)
        attempts_dao = AttemptsDAO(session)
        questions_dao = QuestionsDAO(session)
        
        question = await questions_dao.find_one_or_none_by_id(request.question_id)
        if not question:
            logger.error(f"Question {request.question_id} not found during insider marking for command {request.command_id}")
            raise RiddleNotFoundException 
            
        block_id = question.block_id

        is_assigned = await q_insider_dao.is_question_assigned_to_insider(
            question_id=request.question_id,
            insider_user_id=scanner_user.id
        )
        if not is_assigned:
            logger.warning(f"Вопрос {request.question_id} не назначен инсайдеру {scanner_user.id}")
            raise QuestionNotAssignedException
            
        already_marked = await attempts_dao.has_successful_insider_attempt(
            command_id=request.command_id,
            question_id=request.question_id
        )
        if already_marked:
            logger.warning(f"Посещение вопроса {request.question_id} для команды {request.command_id} уже было отмечено")
            raise AttendanceAlreadyMarkedException
            
        is_solved_by_team = await attempts_dao.has_successful_solve_attempt(
            command_id=request.command_id,
            question_id=request.question_id
        )
        if not is_solved_by_team:
            logger.warning(f"Попытка отметить посещение нерешенной загадки {request.question_id} для команды {request.command_id}")
            raise CannotMarkUnsolvedException
        
        hint_was_used_for_solving = await attempts_dao.has_successful_attempt_of_type(
            command_id=request.command_id,
            question_id=request.question_id,
            attempt_type_name="question_hint"
        )
        
        attempt_type_name = "insider_hint" if hint_was_used_for_solving else "insider"
        logger.info(f"Определен тип отметки инсайдера: {attempt_type_name}")
        
        attempt_type = await attempts_dao.get_attempt_type_by_name(attempt_type_name)
        if not attempt_type:
            logger.error(f"Не удалось найти ID для типа попытки {attempt_type_name}")
            raise AttemptTypeNotFoundException
            
        new_attempt = Attempt(
            user_id=request.scanned_user_id,
            command_id=request.command_id,
            question_id=request.question_id,
            attempt_type_id=attempt_type.id,
            is_true=True,
            attempt_text=f"Marked by insider {scanner_user.id}" 
        )
        session.add(new_attempt)
        await session.commit()
        
        logger.info(f"Посещение вопроса {request.question_id} для команды {request.command_id} успешно отмечено инсайдером {scanner_user.id} с типом {attempt_type_name}")
        
        # --- Check for insider block completion --- 
        try:
            completed = await attempts_dao.try_complete_insider_block(
                command_id=request.command_id,
                block_id=block_id,
                user_id=request.scanned_user_id,
                last_question_id=request.question_id
            )
            if completed:
                logger.info(f"Insider block {block_id} completed by command {request.command_id} after marking question {request.question_id}")
        except Exception as block_complete_exc: 
            logger.error(f"Error during insider block completion check for command {request.command_id}, block {block_id}: {block_complete_exc}", exc_info=True)
        # --- End block completion check ---

        return MarkAttendanceResponse(ok=True, message="Посещение успешно отмечено")
        
    except HTTPException as http_exc:
        raise http_exc    
    except Exception as e:
        logger.error(f"Ошибка при отметке посещения инсайдером {scanner_user.id} (вопрос {request.question_id}, команда {request.command_id}): {str(e)}", exc_info=True)
        await session.rollback()
        raise InternalServerErrorException

@router.get("/events/{event_name}/answers", response_model=EventQuestStructureResponse)
async def get_event_quest_structure(
    event_name: str,
    session: AsyncSession = Depends(get_session_with_commit),
):
    """
    Возвращает полную структуру блоков и загадок для указанного события.
    Доступно только организаторам.
    """
    try:
        events_dao = EventsDAO(session)
        # Сначала получаем ID события по имени
        event_id = await events_dao.get_event_id_by_name(event_name)
        if not event_id:
            logger.warning(f"Событие '{event_name}' не найдено при запросе структуры квеста (ID не найден).")
            raise EventNotFoundException(detail=f"Event '{event_name}' not found.")
        # Затем получаем сам объект события по ID
        event = await events_dao.find_one_or_none_by_id(event_id)
        if not event:
            # Эта ситуация маловероятна, если ID был найден, но лучше проверить
            logger.error(f"Событие с ID {event_id} (имя: '{event_name}') не найдено после получения ID.")
            raise EventNotFoundException(detail=f"Event '{event_name}' (ID: {event_id}) could not be fetched.")

        logger.info(f"Найдено событие '{event_name}' с ID {event_id}")

        # Получаем только ID языков напрямую, чтобы избежать ошибки в find_all
        language_query = select(Language.id)
        language_result = await session.execute(language_query)
        event_language_ids = language_result.scalars().all()

        if not event_language_ids:
            logger.info(f"Для события '{event_name}' не найдено языков. Возвращаем пустую структуру.")
            return EventQuestStructureResponse(event_name=event_name, blocks=[])

        logger.info(f"Найдены ID языков для события '{event_name}': {event_language_ids}")

        # --- Изменено начало: Заменяем blocks_dao.find_all на явный select с options ---
        stmt = (
            select(Block)
            .where(Block.language_id.in_(event_language_ids))
            .options(selectinload(Block.questions))
            # .order_by(Block.order) # Сортировка будет применена позже
        )
        result = await session.execute(stmt)
        blocks = result.scalars().unique().all()
        # --- Изменено конец ---

        logger.info(f"Найдено {len(blocks)} блоков для языков события '{event_name}'")

        # Собираем все ID вопросов из блоков
        all_question_ids = []
        # --- НОВОЕ: Создаём словарь для маппинга вопросов на языки блоков ---
        question_to_language_map = {}
        for block in blocks:
            for question in block.questions:
                all_question_ids.append(question.id)
                question_to_language_map[question.id] = block.language_id
            
        # --- ИЗМЕНЕНО: Получаем статистику решений с учетом языка команд ---
        attempts_dao = AttemptsDAO(session)
        solve_stats = await attempts_dao.get_question_solve_stats_by_language(
            all_question_ids, 
            question_to_language_map, 
            event_id
        )
        logger.info(f"Получена статистика решений для {len(solve_stats)} вопросов с учетом языка команд")

        response_blocks = []
        for block in blocks:
            # Вопросы уже загружены благодаря selectinload
            response_questions = [
                QuestionStructureInfo(
                    id=q.id,
                    title=q.title,
                    image_path=q.image_path,
                    hint_path=q.hint_path,
                    longread=q.longread,
                    image_path_answered=q.image_path_answered,
                    solved_percent=solve_stats.get(q.id, 0.0)
                )
                for q in sorted(block.questions, key=lambda x: x.id) # Sort questions for consistency
            ]
            
            response_blocks.append(
                BlockStructureInfo(
                    id=block.id,
                    title=block.title,
                    image_path=block.image_path,
                    language_id=block.language_id,
                    questions=response_questions,
                )
            )

        logger.info(f"Структура квеста для события '{event_name}' успешно сформирована.")
        # Явно преобразуем в словарь перед возвратом
        response_data = EventQuestStructureResponse(event_name=event_name, blocks=response_blocks)
        return response_data.model_dump()

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Ошибка при получении структуры квеста для события '{event_name}'")
        raise InternalServerErrorException

