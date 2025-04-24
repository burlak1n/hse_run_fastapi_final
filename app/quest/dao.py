from app.logger import logger
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.quest.models import Answer, Block, Question, QuestionInsider, Attempt, AttemptType
from app.auth.models import User
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

class BlocksDAO(BaseDAO):
    model = Block

    async def find_all(self, filters: BaseModel | None = None):
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
        logger.info(f"Поиск всех записей {self.model.__name__} по фильтрам: {filter_dict}")
        try:
            query = select(self.model).filter_by(**filter_dict)
            result = await self._session.execute(query)
            records = result.unique().scalars().all()  # Добавлен вызов unique()
            logger.info(f"Найдено {len(records)} записей.")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске всех записей по фильтрам {filter_dict}: {e}")
            raise
        
class QuestionsDAO(BaseDAO):
    """DAO для работы с вопросами"""
    
    model = Question
    
    async def get_all_questions(self) -> List[Question]:
        """Возвращает все вопросы"""
        stmt = select(Question).order_by(Question.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_questions_by_block(self, block_id: int) -> List[Question]:
        """Возвращает все вопросы в блоке"""
        stmt = select(Question).where(Question.block_id == block_id).order_by(Question.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_block_id(self, block_id: int):
        """Находит все вопросы для указанного блока"""
        try:
            query = select(self.model).where(self.model.block_id == block_id)
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info(f"Найдено {len(records)} вопросов для блока {block_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске вопросов для блока {block_id}: {e}")
            raise

class AnswersDAO(BaseDAO):
    model = Answer

    async def find_by_question_id(self, question_id: int):
        """Находит все ответы для указанного вопроса"""
        try:
            query = select(self.model).where(self.model.question_id == question_id)
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info(f"Найдено {len(records)} ответов для вопроса {question_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске ответов для вопроса {question_id}: {e}")
            raise

class QuestionInsiderDAO(BaseDAO):
    model = QuestionInsider

    async def find_by_question_id(self, question_id: int):
        """Находит всех инсайдеров для указанного вопроса"""
        try:
            query = select(self.model).where(self.model.question_id == question_id)
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info(f"Найдено {len(records)} инсайдеров для вопроса {question_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске инсайдеров для вопроса {question_id}: {e}")
            raise

    async def find_questions_by_insider(self, insider_user_id: int) -> List[Question]:
        """Находит все вопросы (объекты Question), назначенные указанному инсайдеру."""
        try:
            query = (
                select(Question)
                .join(QuestionInsider, QuestionInsider.question_id == Question.id)
                .where(QuestionInsider.user_id == insider_user_id)
                .options(selectinload(Question.answers)) # Пример загрузки связей, если нужно
            )
            result = await self._session.execute(query)
            records = result.scalars().unique().all()
            logger.info(f"Найдено {len(records)} вопросов для инсайдера {insider_user_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске вопросов для инсайдера {insider_user_id}: {e}")
            raise

    async def is_question_assigned_to_insider(self, question_id: int, insider_user_id: int) -> bool:
        """Проверяет, назначен ли конкретный вопрос конкретному инсайдеру."""
        try:
            query = select(QuestionInsider).where(
                QuestionInsider.question_id == question_id,
                QuestionInsider.user_id == insider_user_id
            )
            result = await self._session.execute(query)
            exists = result.scalar_one_or_none() is not None
            logger.debug(f"Проверка назначения вопроса {question_id} инсайдеру {insider_user_id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при проверке назначения вопроса {question_id} инсайдеру {insider_user_id}: {e}")
            raise

class AttemptsDAO(BaseDAO):
    model = Attempt

    async def find_by_command_and_question(self, command_id: int, question_id: int):
        """Находит все попытки для указанной команды и вопроса"""
        try:
            query = select(self.model).where(
                self.model.command_id == command_id,
                self.model.question_id == question_id
            ).options(selectinload(self.model.attempt_type)) # Загружаем тип попытки
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info(f"Найдено {len(records)} попыток для команды {command_id} и вопроса {question_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске попыток для команды {command_id} и вопроса {question_id}: {e}")
            raise

    async def has_successful_attempt_of_type(self, command_id: int, question_id: int, attempt_type_name: str) -> bool:
        """Проверяет, есть ли успешная попытка заданного типа для команды и вопроса."""
        try:
            query = select(Attempt).join(AttemptType).where(
                Attempt.command_id == command_id,
                Attempt.question_id == question_id,
                Attempt.is_true == True,
                AttemptType.name == attempt_type_name
            )
            result = await self._session.execute(query)
            exists = result.scalar_one_or_none() is not None
            logger.debug(f"Проверка успешной попытки типа '{attempt_type_name}' для команды {command_id}, вопроса {question_id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при проверке попытки типа '{attempt_type_name}' для команды {command_id}, вопроса {question_id}: {e}")
            raise

    async def has_successful_insider_attempt(self, command_id: int, question_id: int) -> bool:
        """Проверяет, есть ли успешная попытка типа insider или insider_hint для команды и вопроса."""
        try:
            query = select(Attempt).join(AttemptType).where(
                Attempt.command_id == command_id,
                Attempt.question_id == question_id,
                Attempt.is_true == True,
                AttemptType.name.in_(["insider", "insider_hint"])
            )
            result = await self._session.execute(query)
            exists = result.scalar_one_or_none() is not None
            logger.debug(f"Проверка успешной insider/insider_hint попытки для команды {command_id}, вопроса {question_id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при проверке insider/insider_hint попытки для команды {command_id}, вопроса {question_id}: {e}")
            raise

    async def has_successful_solve_attempt(self, command_id: int, question_id: int) -> bool:
        """Проверяет, есть ли успешная попытка решения (question/question_hint) для команды и вопроса."""
        try:
            query = select(Attempt).join(AttemptType).where(
                Attempt.command_id == command_id,
                Attempt.question_id == question_id,
                Attempt.is_true == True,
                AttemptType.name.in_(["question", "question_hint"])
            )
            result = await self._session.execute(query)
            exists = result.scalar_one_or_none() is not None
            logger.debug(f"Проверка успешной question/question_hint попытки для команды {command_id}, вопроса {question_id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при проверке question/question_hint попытки для команды {command_id}, вопроса {question_id}: {e}")
            raise

    async def get_attempt_type_id_by_name(self, type_name: str) -> Optional[int]:
        """Получает ID типа попытки по его имени."""
        try:
            query = select(AttemptType.id).where(AttemptType.name == type_name)
            result = await self._session.execute(query)
            type_id = result.scalar_one_or_none()
            if not type_id:
                logger.warning(f"Тип попытки '{type_name}' не найден.")
            return type_id
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении ID типа попытки '{type_name}': {e}")
            raise
