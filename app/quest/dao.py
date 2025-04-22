from app.logger import logger
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.quest.models import Answer, Block, Question, QuestionInsider
from app.auth.models import User
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any

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
