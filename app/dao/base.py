from typing import List, TypeVar, Generic, Type, Optional
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy import update as sqlalchemy_update, delete as sqlalchemy_delete, func
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from .database import Base

T = TypeVar("T", bound=Base)


class BaseDAO(Generic[T]):
    model: Type[T] = None

    def __init__(self, session: AsyncSession):
        self._session = session
        if self.model is None:
            raise ValueError("Модель должна быть указана в дочернем классе")

    async def find_one_or_none_by_id(self, data_id: int):
        try:
            # Проверяем, что ID целое число
            if not isinstance(data_id, int) or data_id < 0:
                logger.error(f"Недопустимый ID: {data_id}")
                raise ValueError("Недопустимый ID")
                
            query = select(self.model).filter_by(id=data_id)
            result = await self._session.execute(query)
            record = result.unique().scalar_one_or_none()
            log_message = f"Запись {self.model.__name__} с ID {data_id} {'найдена' if record else 'не найдена'}."
            logger.info(log_message)
            return record
        except SQLAlchemyError as e:
            # Include model name and ID in error log
            logger.exception(f"DB error finding {self.model.__name__} by ID {data_id}")
            raise

    async def find_one_or_none(self, filters: BaseModel) -> Optional[T]:
        try:
            filter_dict = filters.model_dump(exclude_unset=True)
            # Проверяем входные данные
            # filter_dict = await self._validate_input(filter_dict)
            
            logger.info(f"Поиск одной записи {self.model.__name__} по фильтрам: {filter_dict}")
            query = select(self.model).filter_by(**filter_dict)
            result = await self._session.execute(query)
            record = result.unique().scalar_one_or_none()
            log_message = f"Запись {'найдена' if record else 'не найдена'} по фильтрам: {filter_dict}"
            logger.info(log_message)
            return record
        except SQLAlchemyError as e:
            # Include model name and filter keys in error log
            logger.exception(f"DB error finding {self.model.__name__} with filters {list(filter_dict.keys())}")
            raise

    async def find_all(self, filters: BaseModel | None = None):
        try:
            filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
            # Проверяем входные данные
            # filter_dict = await self._validate_input(filter_dict)
            
            logger.info(f"Поиск всех записей {self.model.__name__} по фильтрам: {filter_dict}")
            query = select(self.model).filter_by(**filter_dict)
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info(f"Найдено {len(records)} записей.")
            return records
        except SQLAlchemyError as e:
            # Include model name and filter keys in error log
            logger.exception(f"DB error finding all {self.model.__name__} with filters {list(filter_dict.keys())}")
            raise

    async def add(self, values: BaseModel):
        try:
            values_dict = values.model_dump(exclude_unset=True)
            # values_dict = await self._validate_input(values_dict) # Removed validation call
            
            # Log keys being added, not values for security
            logger.info(f"Adding {self.model.__name__} with keys: {list(values_dict.keys())}")
            new_instance = self.model(**values_dict)
            self._session.add(new_instance)
            # Log successful add before flush
            logger.info(f"{self.model.__name__} instance prepared for add.") 
            await self._session.flush()
            # Log after successful flush, potentially with the new ID if available
            logger.info(f"{self.model.__name__} added successfully with ID: {getattr(new_instance, 'id', '?')}")
            return new_instance
        except SQLAlchemyError as e:
            # Include model name and keys being added in error log
            logger.exception(f"DB error adding {self.model.__name__} with keys {list(values_dict.keys())}")
            await self._session.rollback() # Ensure rollback on error
            raise

    async def add_many(self, instances: List[BaseModel]):
        values_list = [item.model_dump(exclude_unset=True) for item in instances]
        logger.info(f"Добавление нескольких записей {self.model.__name__}. Количество: {len(values_list)}")
        try:
            new_instances = [self.model(**values) for values in values_list]
            self._session.add_all(new_instances)
            logger.info(f"Успешно добавлено {len(new_instances)} записей.")
            await self._session.flush()
            return new_instances
        except SQLAlchemyError as e:
            # Include model name in error log
            logger.exception(f"DB error adding many {self.model.__name__}")
            await self._session.rollback()
            raise

    async def update(self, filters: BaseModel, values: BaseModel):
        filter_dict = filters.model_dump(exclude_unset=True)
        values_dict = values.model_dump(exclude_unset=True)
        # Log filter keys and keys being updated
        logger.info(
            f"Updating {self.model.__name__} filtered by {list(filter_dict.keys())} with keys: {list(values_dict.keys())}")
        try:
            query = (
                sqlalchemy_update(self.model)
                .where(*[getattr(self.model, k) == v for k, v in filter_dict.items()])
                .values(**values_dict)
                .execution_options(synchronize_session="fetch")
            )
            result = await self._session.execute(query)
            logger.info(f"Обновлено {result.rowcount} записей.")
            await self._session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            # Include model name, filter keys, and updated keys in error log
            logger.exception(f"DB error updating {self.model.__name__} filtered by {list(filter_dict.keys())} with keys {list(values_dict.keys())}")
            await self._session.rollback()
            raise

    async def delete(self, filters: BaseModel):
        filter_dict = filters.model_dump(exclude_unset=True)
        # Log filter keys being used for deletion
        logger.info(f"Deleting {self.model.__name__} filtered by {list(filter_dict.keys())}")
        if not filter_dict:
            logger.error("Delete operation requires at least one filter.")
            raise ValueError("Нужен хотя бы один фильтр для удаления.")
        try:
            query = sqlalchemy_delete(self.model).filter_by(**filter_dict)
            result = await self._session.execute(query)
            logger.info(f"Удалено {result.rowcount} записей.")
            await self._session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            # Include model name and filter keys in error log
            logger.exception(f"DB error deleting {self.model.__name__} filtered by {list(filter_dict.keys())}")
            await self._session.rollback()
            raise

    async def count(self, filters: BaseModel | None = None):
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
        logger.info(f"Подсчет количества записей {self.model.__name__} по фильтру: {filter_dict}")
        try:
            query = select(func.count(self.model.id)).filter_by(**filter_dict)
            result = await self._session.execute(query)
            count = result.scalar()
            logger.info(f"Найдено {count} записей.")
            return count
        except SQLAlchemyError as e:
            # Include model name and filter keys in error log
            logger.exception(f"DB error counting {self.model.__name__} filtered by {list(filter_dict.keys())}")
            raise

    async def bulk_update(self, records: List[BaseModel]):
        logger.info(f"Массовое обновление записей {self.model.__name__}")
        try:
            updated_count = 0
            for record in records:
                record_dict = record.model_dump(exclude_unset=True)
                if 'id' not in record_dict:
                    continue

                update_data = {k: v for k, v in record_dict.items() if k != 'id'}
                stmt = (
                    sqlalchemy_update(self.model)
                    .filter_by(id=record_dict['id'])
                    .values(**update_data)
                )
                result = await self._session.execute(stmt)
                updated_count += result.rowcount

            logger.info(f"Обновлено {updated_count} записей")
            await self._session.flush()
            return updated_count
        except SQLAlchemyError as e:
            # Include model name in error log
            logger.exception(f"DB error during bulk update of {self.model.__name__}")
            await self._session.rollback()
            raise
