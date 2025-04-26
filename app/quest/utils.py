import re

from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import Command
from app.quest.models import Block, Question
from app.quest.dao import BlocksDAO, QuestionsDAO, AnswersDAO, QuestionInsiderDAO, AttemptsDAO
from app.quest.schemas import FindQuestionsForBlock
from app.logger import logger


def normalize_text(text: str) -> set[str]:
    # Извлекаем слова и сразу возвращаем множество
    return set(re.findall(r'\b\w+\b', text.lower()))

def compare_strings(str1: str, str2: str) -> bool:
    # Сравниваем множества слов
    return normalize_text(str1) == normalize_text(str2)

# --- Вспомогательные функции для сборки ответа --- 

async def build_block_response(block: Block, command: Command, include_riddles: bool = False, session: AsyncSession = None) -> dict:
    """Создание структуры ответа для блока (принимает command) -- Теперь в utils"""
    if not session:
        logger.error("Сессия не передана в build_block_response")
        # Лучше выбросить исключение или вернуть ошибку явно
        return {
            "id": block.id,
            "title": block.title,
            "language_id": block.language_id,
            "error": "Failed to calculate progress (no session)"
        }

    questions_dao = QuestionsDAO(session)
    attempts_dao = AttemptsDAO(session)

    response = {
        "id": block.id,
        "title": block.title,
        "language_id": block.language_id
    }
    if include_riddles:
        # Вызываем get_riddles_for_block (определение ниже)
        response['riddles'] = await get_riddles_for_block(block.id, session, command.id)
    else:
        # Используем методы DAO для счетчиков
        solved = await attempts_dao.get_solved_riddles_count(block.id, command.id)
        total = await questions_dao.get_total_riddles_count(block.id)
        insider = await attempts_dao.get_insider_riddles_count(block.id, command.id)
        response['solved_count'] = solved
        response['total_count'] = total
        response['insider_count'] = insider
        response['progress'] = round((solved / total) * 100) if total > 0 else 0
    return response

async def get_riddle_data(question: Question, attempt_statuses: dict, session: AsyncSession) -> dict:
    """Формирует данные загадки, используя предзагруженные статусы попыток -- Теперь в utils."""
    # Получаем статусы из словаря
    solved = question.id in attempt_statuses.get("solved", set())
    has_hint = question.id in attempt_statuses.get("hint_used", set())
    has_insider_attempt = question.id in attempt_statuses.get("insider_visited", set())

    if solved:
        # Для решенных загадок возвращаем полные данные
        
        # --- Get insider links (plural) --- 
        insider_links = [] # Initialize as list
        try:
            insider_dao = QuestionInsiderDAO(session)
            insiders_with_info = await insider_dao.find_by_question_id_with_user_and_info(question.id)
            
            if insiders_with_info:
                for qi in insiders_with_info: # Iterate through all found insiders
                    insider_user = qi.user
                    if insider_user and insider_user.insider_info and insider_user.insider_info.geo_link:
                        insider_links.append(insider_user.insider_info.geo_link) # Add link to list
                        logger.debug(f"Insider link found for question {question.id}: {insider_user.insider_info.geo_link}")
                    else:
                        logger.warning(f"Insider {qi.id} found for question {question.id}, but no user, insider_info, or geo_link.")
            else:
                 logger.debug(f"No insiders found for question {question.id}.")
                 
            if not insider_links:
                 logger.debug(f"No valid insider links collected for question {question.id}.")
                 
        except Exception as e:
            logger.error(f"Error fetching insider links for question {question.id}: {e}", exc_info=True)
        # --- End get insider links ---
        
        return {
            "id": question.id,
            "title": question.title,
            "text_answered": question.text_answered,
            "image_path_answered": question.image_path_answered,
            "geo_answered": question.geo_answered,
            "insiderLinks": insider_links, # Use the new list field name
            "has_insider_attempt": has_insider_attempt,
            "has_hint": has_hint and question.hint_path is not None,
            "hint": question.hint_path if has_hint else None
        }
    else:
        # Для нерешенных загадок возвращаем только базовую информацию и статус подсказки
        return {
            "id": question.id,
            "image_path": question.image_path,
            "has_hint": has_hint and question.hint_path is not None,
            "hint": question.hint_path if has_hint else None
        }

async def get_riddles_for_block(block_id: int, session: AsyncSession, command_id: int) -> list:
    """
    Получает список вопросов для указанного блока, оптимизируя запросы статусов попыток -- Теперь в utils.
    """
    questions_dao = QuestionsDAO(session)
    attempts_dao = AttemptsDAO(session)

    # 1. Получаем все вопросы для блока
    questions = await questions_dao.find_all(filters=FindQuestionsForBlock(block_id=block_id))
    if not questions:
        return []

    # 2. Собираем ID вопросов
    question_ids = [q.id for q in questions]

    # 3. Получаем все статусы попыток для этих вопросов одним запросом
    attempt_statuses = await attempts_dao.get_attempts_status_for_block(command_id, question_ids)

    # 4. Формируем результат, передавая каждой загадке общий словарь статусов и сессию
    result = []
    for question in questions:
        result.append(await get_riddle_data(question, attempt_statuses, session))

    return result
