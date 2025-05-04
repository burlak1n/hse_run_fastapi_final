from app.logger import logger
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.quest.models import Answer, Block, Question, QuestionInsider, Attempt, AttemptType
from app.auth.models import User, Command
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

    async def get_total_riddles_count(self, block_id: int) -> int:
        """Получает общее количество загадок в блоке"""
        try:
            query = select(func.count(self.model.id)).where(self.model.block_id == block_id)
            result = await self._session.execute(query)
            count = result.scalar_one()
            logger.debug(f"Общее количество загадок в блоке {block_id}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при подсчете общего количества загадок в блоке {block_id}: {e}")
            raise

    async def get_total_insider_riddles_count(self, block_id: int) -> int:
        """Получает общее количество загадок в блоке, у которых есть хотя бы один назначенный инсайдер."""
        try:
            query = (
                select(func.count(Question.id.distinct()))
                .join(QuestionInsider, Question.id == QuestionInsider.question_id)
                .where(Question.block_id == block_id)
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            logger.debug(f"Общее количество инсайдерских загадок в блоке {block_id}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при подсчете инсайдерских загадок в блоке {block_id}: {e}")
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

    async def find_by_question_id_with_user_and_info(self, question_id: int) -> List[QuestionInsider]:
        """Находит всех инсайдеров для вопроса с загрузкой User и InsiderInfo."""
        try:
            query = (
                select(self.model)
                .where(self.model.question_id == question_id)
                .options(
                    selectinload(self.model.user)
                    .selectinload(User.insider_info) # Загружаем User, затем InsiderInfo
                )
            )
            result = await self._session.execute(query)
            records = result.unique().scalars().all()
            logger.info(f"Найдено {len(records)} инсайдеров с user+info для вопроса {question_id}")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске инсайдеров с user+info для вопроса {question_id}: {e}")
            raise

    async def find_questions_by_insider(self, insider_user_id: int) -> List[Question]:
        """Находит все вопросы (объекты Question), назначенные указанному инсайдеру."""
        try:
            query = (
                select(Question)
                .join(QuestionInsider, QuestionInsider.question_id == Question.id)
                .where(QuestionInsider.user_id == insider_user_id)
                .options(selectinload(Question.answers), selectinload(Question.block))
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

    async def get_attempt_type_by_name(self, type_name: str) -> Optional[AttemptType]:
        """Получает объект AttemptType по его имени."""
        try:
            query = select(AttemptType).where(AttemptType.name == type_name)
            result = await self._session.execute(query)
            attempt_type = result.scalar_one_or_none()
            if not attempt_type:
                logger.warning(f"Тип попытки '{type_name}' не найден.")
            return attempt_type
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении объекта AttemptType по имени '{type_name}': {e}")
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

    async def get_solved_riddles_count(self, block_id: int, command_id: int) -> int:
        """Получает количество решённых загадок в блоке для команды (типы question/question_hint)."""
        try:
            query = (
                select(func.count(Attempt.id))
                .join(Question, Question.id == Attempt.question_id)
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Question.block_id == block_id,
                    Attempt.command_id == command_id,
                    Attempt.is_true == True,
                    AttemptType.name.in_(["question", "question_hint"])
                )
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            logger.debug(f"Количество решенных загадок в блоке {block_id} для команды {command_id}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка подсчета решенных загадок в блоке {block_id} для команды {command_id}: {e}")
            raise

    async def get_insider_riddles_count(self, block_id: int, command_id: int) -> int:
        """Получает количество загадок, на которые приехали (типы insider/insider_hint)."""
        try:
            query = (
                select(func.count(Attempt.id))
                .join(Question, Question.id == Attempt.question_id)
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Question.block_id == block_id,
                    Attempt.command_id == command_id,
                    Attempt.is_true == True,
                    AttemptType.name.in_(["insider", "insider_hint"])
                )
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            logger.debug(f"Количество посещенных инсайдерских локаций в блоке {block_id} для команды {command_id}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка подсчета посещенных инсайдерских локаций в блоке {block_id} для команды {command_id}: {e}")
            raise

    async def get_solved_riddles_count_for_command(self, command_id: int) -> int:
        """Получает общее количество решённых загадок для команды (типы question/question_hint)."""
        try:
            query = (
                select(func.count(Attempt.id))
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Attempt.command_id == command_id,
                    Attempt.is_true == True,
                    AttemptType.name.in_(["question", "question_hint"])
                )
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            logger.debug(f"Общее количество решенных загадок для команды {command_id}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка подсчета решенных загадок для команды {command_id}: {e}")
            raise

    async def calculate_team_score_and_coins(self, command_id: int) -> Dict[str, int]:
        """Вычисляет счёт и количество монет команды на основе успешных попыток."""
        try:
            query = (
                select(func.sum(AttemptType.score), func.sum(AttemptType.money))
                .join(Attempt, Attempt.attempt_type_id == AttemptType.id)
                .where(Attempt.command_id == command_id, Attempt.is_true == True)
            )
            result = await self._session.execute(query)
            scores_and_coins = result.first() # Используем first() для агрегирующих функций

            total_score = scores_and_coins[0] if scores_and_coins and scores_and_coins[0] is not None else 0
            total_coins = scores_and_coins[1] if scores_and_coins and scores_and_coins[1] is not None else 0

            logger.debug(f"Расчет статистики для команды {command_id}: score={total_score}, coins={total_coins}")
            return {"score": total_score, "coins": total_coins}
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при расчете статистики для команды {command_id}: {e}")
            raise

    async def has_successful_block_attempt(self, command_id: int, block_id: int, block_attempt_type_id: int) -> bool:
        """Проверяет, есть ли успешная попытка завершения блока (question_block/insider_block) для команды."""
        try:
            query = (
                select(Attempt.id) # Достаточно выбрать ID для проверки существования
                .join(Question, Attempt.question_id == Question.id)
                .where(
                    Attempt.command_id == command_id,
                    Question.block_id == block_id,
                    Attempt.attempt_type_id == block_attempt_type_id,
                    Attempt.is_true == True
                )
                .limit(1) # Нам нужна только одна запись для подтверждения
            )
            result = await self._session.execute(query)
            exists = result.scalar_one_or_none() is not None
            logger.debug(f"Проверка успешной попытки завершения блока {block_id} (тип {block_attempt_type_id}) для команды {command_id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при проверке попытки завершения блока {block_id} для команды {command_id}: {e}")
            raise

    async def get_attempts_status_for_block(self, command_id: int, question_ids: list[int]) -> dict:
        """
        Получает статусы (решено, подсказка использована, инсайдер посещен)
        для списка вопросов в блоке для указанной команды одним запросом.
        """
        if not question_ids:
            return {"solved": set(), "hint_used": set(), "insider_visited": set()}

        try:
            # Типы попыток, которые нам нужны для определения статусов
            relevant_types = ["question", "question_hint", "hint", "insider", "insider_hint"]

            query = (
                select(Attempt.question_id, AttemptType.name)
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Attempt.command_id == command_id,
                    Attempt.question_id.in_(question_ids),
                    Attempt.is_true == True,
                    AttemptType.name.in_(relevant_types)
                )
                .distinct() # Убеждаемся, что не дублируем пары (question_id, type_name)
            )

            result = await self._session.execute(query)
            attempts_data = result.all()

            solved_ids = set()
            hint_used_ids = set()
            insider_visited_ids = set()

            for qid, type_name in attempts_data:
                if type_name in ["question", "question_hint"]:
                    solved_ids.add(qid)
                if type_name == "hint":
                    hint_used_ids.add(qid)
                if type_name in ["insider", "insider_hint"]:
                    insider_visited_ids.add(qid)

            logger.debug(f"Статусы попыток для команды {command_id} и вопросов {question_ids}: решено={len(solved_ids)}, подсказка={len(hint_used_ids)}, инсайдер={len(insider_visited_ids)}")

            return {
                "solved": solved_ids,
                "hint_used": hint_used_ids,
                "insider_visited": insider_visited_ids
            }
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении статусов попыток для команды {command_id} и вопросов {question_ids}: {e}")
            # Возвращаем пустые множества в случае ошибки, чтобы избежать падения выше
            return {"solved": set(), "hint_used": set(), "insider_visited": set()}

    async def get_all_successful_attempts_for_commands(self, command_ids: list[int]) -> List[tuple]:
        """Получает command_id, тип попытки, очки и монеты для всех успешных попыток указанных команд."""
        if not command_ids:
            return []
        try:
            query = (
                select(
                    Attempt.command_id,
                    AttemptType.name,
                    AttemptType.score,
                    AttemptType.money
                )
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Attempt.command_id.in_(command_ids),
                    Attempt.is_true == True
                )
            )
            result = await self._session.execute(query)
            attempts_data = result.all()
            logger.debug(f"Получено {len(attempts_data)} успешных попыток для команд {command_ids}")
            return attempts_data
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении всех успешных попыток для команд {command_ids}: {e}")
            raise

    async def get_aggregated_scores_for_commands(self, command_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """
        Вычисляет агрегированные базовые очки (sum(score)) и монеты (sum(money))
        для списка команд на основе их успешных попыток.
        Возвращает словарь {command_id: {"base_score": ..., "coins": ...}}.
        """
        if not command_ids:
            return {}
        try:
            query = (
                select(
                    Attempt.command_id,
                    func.sum(AttemptType.score).label("base_score"),
                    func.sum(AttemptType.money).label("coins")
                )
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Attempt.command_id.in_(command_ids),
                    Attempt.is_true == True
                )
                .group_by(Attempt.command_id)
            )
            result = await self._session.execute(query)
            # Создаем словарь с результатами, обрабатывая None значения
            aggregated_data = {
                row.command_id: {
                    "base_score": int(row.base_score) if row.base_score is not None else 0,
                    "coins": int(row.coins) if row.coins is not None else 0
                }
                for row in result.all()
            }
            logger.debug(f"Получены агрегированные score/coins для {len(aggregated_data)} команд из {len(command_ids)} запрошенных.")
            return aggregated_data
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при агрегации score/coins для команд {command_ids}: {e}")
            raise # Передаем ошибку выше

    async def try_complete_question_block(self, command_id: int, block_id: int, user_id: int, last_question_id: int) -> bool:
        """
        Проверяет, завершен ли блок вопросов командой, и если да,
        создает попытку 'question_block', если она еще не существует.
        Возвращает True, если попытка была создана, иначе False.
        """
        try:
            # Получаем ID типа попытки 'question_block'
            question_block_type_id = await self.get_attempt_type_id_by_name("question_block")
            if not question_block_type_id:
                logger.error(f"Не найден тип попытки 'question_block' для команды {command_id}, блока {block_id}")
                return False

            # Проверяем, не была ли попытка уже создана
            block_already_completed = await self.has_successful_block_attempt(
                command_id=command_id,
                block_id=block_id,
                block_attempt_type_id=question_block_type_id
            )
            if block_already_completed:
                logger.info(f"Question Block {block_id} уже был отмечен как завершенный для команды {command_id}.")
                return False

            # Получаем счетчики
            solved_count = await self.get_solved_riddles_count(block_id, command_id)
            # Используем QuestionsDAO для получения общего числа вопросов
            questions_dao = QuestionsDAO(self._session) # Создаем экземпляр с той же сессией
            total_count = await questions_dao.get_total_riddles_count(block_id)

            logger.info(f"Question Block {block_id} completion check for command {command_id}: {solved_count}/{total_count} riddles solved.")

            # Проверяем условие завершения
            if solved_count == total_count and total_count > 0:
                logger.info(f"Question Block {block_id} completed by command {command_id}. Creating 'question_block' attempt.")
                block_attempt = Attempt(
                    user_id=user_id,
                    command_id=command_id,
                    question_id=last_question_id, # Привязываем к последней решенной загадке
                    attempt_type_id=question_block_type_id,
                    is_true=True,
                    attempt_text=f"Block {block_id} completed"
                )
                self._session.add(block_attempt)
                await self._session.commit() # Коммитим завершение блока
                logger.info(f"Question Block {block_id} attempt successfully created for command {command_id}.")
                return True # Попытка создана
            else:
                 logger.info(f"Question Block {block_id} completion condition not met for command {command_id} ({solved_count}/{total_count}).")
                 return False # Условие не выполнено

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemyError при попытке завершить Question Block {block_id} для команды {command_id}: {e}", exc_info=True)
            await self._session.rollback() # Откат в случае ошибки
            return False # Ошибка при выполнении
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при попытке завершить Question Block {block_id} для команды {command_id}: {e}", exc_info=True)
            await self._session.rollback() # Откат в случае ошибки
            return False # Ошибка при выполнении

    async def try_complete_insider_block(self, command_id: int, block_id: int, user_id: int, last_question_id: int) -> bool:
        """
        Проверяет, завершен ли инсайдерский блок командой, и если да,
        создает попытку 'insider_block', если она еще не существует.
        Возвращает True, если попытка была создана, иначе False.
        """
        try:
            # Получаем ID типа попытки 'insider_block'
            insider_block_type_id = await self.get_attempt_type_id_by_name("insider_block")
            if not insider_block_type_id:
                logger.error(f"Не найден тип попытки 'insider_block' для команды {command_id}, блока {block_id}")
                return False

            # Проверяем, не была ли попытка уже создана
            block_already_completed = await self.has_successful_block_attempt(
                command_id=command_id,
                block_id=block_id,
                block_attempt_type_id=insider_block_type_id
            )
            if block_already_completed:
                logger.info(f"Insider Block {block_id} уже был отмечен как завершенный для команды {command_id}.")
                return False

            # Получаем счетчики
            visited_count = await self.get_insider_riddles_count(block_id, command_id)
            # Используем QuestionsDAO для получения общего числа инсайдерских вопросов
            questions_dao = QuestionsDAO(self._session)
            total_count = await questions_dao.get_total_insider_riddles_count(block_id)

            logger.info(f"Insider Block {block_id} completion check for command {command_id}: {visited_count}/{total_count} locations visited.")

            # Проверяем условие завершения
            if visited_count == total_count and total_count > 0:
                logger.info(f"Insider Block {block_id} completed by command {command_id}. Creating 'insider_block' attempt.")
                block_attempt = Attempt(
                    user_id=user_id,
                    command_id=command_id,
                    question_id=last_question_id, # Привязываем к последней посещенной локации
                    attempt_type_id=insider_block_type_id,
                    is_true=True,
                    attempt_text=f"Insider Block {block_id} completed"
                )
                self._session.add(block_attempt)
                await self._session.commit() # Коммитим завершение блока
                logger.info(f"Insider Block {block_id} attempt successfully created for command {command_id}.")
                return True # Попытка создана
            else:
                 logger.info(f"Insider Block {block_id} completion condition not met for command {command_id} ({visited_count}/{total_count}).")
                 return False # Условие не выполнено

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemyError при попытке завершить Insider Block {block_id} для команды {command_id}: {e}", exc_info=True)
            await self._session.rollback()
            return False
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при попытке завершить Insider Block {block_id} для команды {command_id}: {e}", exc_info=True)
            await self._session.rollback()
            return False

    async def get_question_solve_stats(self, question_ids: List[int], event_id: int = None) -> Dict[int, float]:
        """
        Возвращает статистику решений по каждому вопросу: процент команд, решивших вопрос.
        Исключает команды с общим количеством баллов <= 2.
        Возвращает проценты с точностью до одной десятой.
        
        Args:
            question_ids: Список ID вопросов
            event_id: ID события (опционально, для фильтрации по событию)
            
        Returns:
            Dict[int, float]: Словарь {question_id: процент_решивших}
        """
        if not question_ids:
            return {}
            
        try:
            # Получаем команды с их баллами
            commands_with_scores_query = (
                select(
                    Command.id,
                    func.sum(AttemptType.score).label("total_score")
                )
                .join(Attempt, Attempt.command_id == Command.id)
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(Attempt.is_true == True)
                .group_by(Command.id)
                .having(func.sum(AttemptType.score) > 2)  # Фильтруем команды с баллами <= 2
            )
            
            if event_id:
                commands_with_scores_query = commands_with_scores_query.where(Command.event_id == event_id)
                
            result = await self._session.execute(commands_with_scores_query)
            valid_command_ids = [row.id for row in result.all()]
            
            if not valid_command_ids:
                logger.warning(f"Нет команд с баллами > 2 для расчёта статистики решений вопросов")
                return {q_id: 0.0 for q_id in question_ids}
                
            total_commands = len(valid_command_ids)
            logger.info(f"Найдено {total_commands} команд с баллами > 2 для расчёта статистики")
            
            # Запрос для подсчёта успешных попыток по каждому вопросу
            query = (
                select(
                    Attempt.question_id,
                    func.count(func.distinct(Attempt.command_id)).label("solved_count")
                )
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(
                    Attempt.question_id.in_(question_ids),
                    Attempt.command_id.in_(valid_command_ids),
                    Attempt.is_true == True,
                    AttemptType.name.in_(["question", "question_hint"])
                )
                .group_by(Attempt.question_id)
            )
                
            result = await self._session.execute(query)
            
            # Округляем до 1 десятичного знака
            stats = {
                row.question_id: round((row.solved_count / total_commands) * 100, 1) 
                for row in result.all()
            }
            
            # Заполнить нулями для вопросов, которые не были решены ни одной командой
            for q_id in question_ids:
                if q_id not in stats:
                    stats[q_id] = 0.0
                    
            logger.info(f"Получена статистика решений для {len(stats)} вопросов")
            return stats
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении статистики решений вопросов {question_ids}: {e}", exc_info=True)
            return {q_id: 0.0 for q_id in question_ids}

    async def get_question_solve_stats_by_language(self, question_ids: List[int], blocks_language_map: Dict[int, int], event_id: int = None) -> Dict[int, float]:
        """
        Возвращает статистику решений по каждому вопросу с учетом языка блока: 
        процент команд с тем же языком, что и блок, решивших вопрос.
        Исключает команды с общим количеством баллов <= 2.
        
        Args:
            question_ids: Список ID вопросов
            blocks_language_map: Словарь {question_id: language_id} для определения языка каждого вопроса
            event_id: ID события (опционально, для фильтрации по событию)
            
        Returns:
            Dict[int, float]: Словарь {question_id: процент_решивших среди команд с тем же языком}
        """
        if not question_ids or not blocks_language_map:
            return {}
            
        try:
            # Получаем команды с их баллами и языками
            commands_with_scores_query = (
                select(
                    Command.id,
                    Command.language_id,
                    func.sum(AttemptType.score).label("total_score")
                )
                .join(Attempt, Attempt.command_id == Command.id)
                .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                .where(Attempt.is_true == True)
                .group_by(Command.id, Command.language_id)
                .having(func.sum(AttemptType.score) > 2)  # Фильтруем команды с баллами <= 2
            )
            
            if event_id:
                commands_with_scores_query = commands_with_scores_query.where(Command.event_id == event_id)
                
            result = await self._session.execute(commands_with_scores_query)
            # Группируем команды по языкам
            commands_by_language = {}
            for row in result.all():
                if row.language_id not in commands_by_language:
                    commands_by_language[row.language_id] = []
                commands_by_language[row.language_id].append(row.id)
            
            if not commands_by_language:
                logger.warning(f"Нет команд с баллами > 2 для расчёта статистики решений вопросов по языкам")
                return {q_id: 0.0 for q_id in question_ids}
            
            logger.info(f"Найдены команды по языкам: {', '.join([f'{lang_id}: {len(cmds)}' for lang_id, cmds in commands_by_language.items()])}")
            
            # Статистика решений для каждого вопроса
            stats = {}
            
            # Для каждого вопроса получаем его язык и считаем процент решения среди команд этого языка
            for question_id in question_ids:
                question_language_id = blocks_language_map.get(question_id)
                if not question_language_id:
                    logger.warning(f"Не найден язык для вопроса {question_id}, пропускаем статистику")
                    stats[question_id] = 0.0
                    continue
                
                # Получаем команды с этим языком
                commands_with_same_language = commands_by_language.get(question_language_id, [])
                if not commands_with_same_language:
                    logger.info(f"Нет активных команд с языком {question_language_id} для вопроса {question_id}")
                    stats[question_id] = 0.0
                    continue
                
                total_same_language_commands = len(commands_with_same_language)
                
                # Запрос для подсчёта успешных попыток для этого вопроса среди команд с тем же языком
                query = (
                    select(func.count(func.distinct(Attempt.command_id)).label("solved_count"))
                    .join(AttemptType, Attempt.attempt_type_id == AttemptType.id)
                    .where(
                        Attempt.question_id == question_id,
                        Attempt.command_id.in_(commands_with_same_language),
                        Attempt.is_true == True,
                        AttemptType.name.in_(["question", "question_hint"])
                    )
                )
                
                result = await self._session.execute(query)
                solved_count = result.scalar() or 0
                
                # Вычисляем процент и округляем до 1 десятичного знака
                percentage = round((solved_count / total_same_language_commands) * 100, 1) if total_same_language_commands > 0 else 0.0
                stats[question_id] = percentage
                logger.debug(f"Вопрос {question_id} (язык {question_language_id}): решен {solved_count}/{total_same_language_commands} команд = {percentage}%")
            
            logger.info(f"Получена статистика решений по языкам для {len(stats)} вопросов")
            return stats
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении статистики решений вопросов по языкам {question_ids}: {e}", exc_info=True)
            return {q_id: 0.0 for q_id in question_ids}
