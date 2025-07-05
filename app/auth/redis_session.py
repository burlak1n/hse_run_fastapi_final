from datetime import datetime, timezone, timedelta
from typing import Optional, Set, Dict, Any
from faststream.redis import RedisBroker
import secrets
from app.config import settings
from app.logger import logger
from dataclasses import dataclass


@dataclass
class RedisSession:
    """Модель Redis-сессии"""
    user_id: int
    token: str
    expires_at: datetime
    is_active: bool = True
    
    def is_expired(self) -> bool:
        """Проверка, истёк ли срок действия сессии."""
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)
    
    def is_valid(self) -> bool:
        """Проверка, действительна ли сессия."""
        return not self.is_expired() and self.is_active
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для хранения в Redis"""
        return {
            'user_id': str(self.user_id),
            'expires_at': self.expires_at.isoformat(),
            'is_active': str(self.is_active)
        }
    
    @classmethod
    def from_dict(cls, token: str, data: Dict[str, Any]) -> 'RedisSession':
        """Создание объекта из словаря Redis"""
        return cls(
            user_id=int(data['user_id']),
            token=token,
            expires_at=datetime.fromisoformat(data['expires_at']),
            is_active=data['is_active'].lower() == 'true' if isinstance(data['is_active'], str) else bool(data['is_active'])
        )


class RedisSessionService:
    """Сервис для работы с сессиями в Redis"""
    
    def __init__(self, redis_broker: RedisBroker):
        self.broker = redis_broker
        self.session_prefix = "session:"
        self.user_sessions_prefix = "user_sessions:"
        self._redis_client = None
    
    @property
    def redis(self):
        """Получить Redis клиент из FastStream broker"""
        if self._redis_client is None:
            # Создаем Redis клиент напрямую, так как RedisBroker не имеет атрибута redis
            from redis import asyncio as aioredis
            from app.config import settings
            self._redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        return self._redis_client
    
    def _get_session_key(self, token: str) -> str:
        """Получить ключ для сессии"""
        return f"{self.session_prefix}{token}"
    
    def _get_user_sessions_key(self, user_id: int) -> str:
        """Получить ключ для сессий пользователя"""
        return f"{self.user_sessions_prefix}{user_id}"
    
    async def create_session(self, user_id: int) -> str:
        """
        Создает новую сессию для пользователя.
        Если у пользователя уже есть активные сессии, они будут деактивированы.
        Возвращает токен созданной сессии.
        """
        logger.info(f"Создание новой сессии для пользователя {user_id}")
        
        try:
            # Деактивируем все активные сессии пользователя
            await self.deactivate_all_sessions(user_id)
            
            # Создаем новую сессию
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_EXPIRE_SECONDS)
            
            session = RedisSession(
                user_id=user_id,
                token=token,
                expires_at=expires_at,
                is_active=True
            )
            
            # Сохраняем сессию в Redis
            session_key = self._get_session_key(token)
            user_sessions_key = self._get_user_sessions_key(user_id)
            
            # Используем pipeline для атомарности
            async with self.redis.pipeline() as pipe:
                # Сохраняем данные сессии
                pipe.hset(session_key, mapping=session.to_dict())
                # Устанавливаем TTL на сессию
                pipe.expire(session_key, int(settings.SESSION_EXPIRE_SECONDS))
                # Добавляем токен в set активных сессий пользователя
                pipe.sadd(user_sessions_key, token)
                # Устанавливаем TTL на set сессий пользователя
                pipe.expire(user_sessions_key, int(settings.SESSION_EXPIRE_SECONDS))
                
                await pipe.execute()
            
            logger.info(f"Новая сессия успешно создана для пользователя {user_id}")
            return token
            
        except Exception as e:
            logger.error(f"Ошибка при создании сессии: {e}")
            raise
    
    async def get_session(self, token: str) -> Optional[RedisSession]:
        """
        Получает сессию по токену.
        Возвращает None если сессия не найдена или недействительна.
        """
        logger.info(f"Получение сессии по токену {token}")
        
        try:
            session_key = self._get_session_key(token)
            session_data = await self.redis.hgetall(session_key)
            
            if not session_data:
                logger.warning(f"Сессия с токеном {token} не найдена")
                return None
            
            session = RedisSession.from_dict(token, session_data)
            
            if not session.is_valid():
                logger.warning(f"Недействительная или истекшая сессия с токеном {token}")
                # Удаляем недействительную сессию
                await self.deactivate_session(token)
                return None
            
            logger.info(f"Сессия с токеном {token} успешно получена")
            return session
            
        except Exception as e:
            logger.error(f"Ошибка при получении сессии: {e}")
            return None
    
    async def deactivate_session(self, token: str) -> bool:
        """
        Деактивирует сессию по токену.
        Возвращает True если сессия была деактивирована.
        """
        logger.info(f"Деактивация сессии с токеном {token}")
        
        try:
            session_key = self._get_session_key(token)
            
            # Получаем данные сессии чтобы найти user_id
            session_data = await self.redis.hgetall(session_key)
            if not session_data:
                logger.warning(f"Сессия с токеном {token} не найдена для деактивации")
                return False
            
            user_id = int(session_data['user_id'])
            user_sessions_key = self._get_user_sessions_key(user_id)
            
            # Используем pipeline для атомарности
            async with self.redis.pipeline() as pipe:
                # Удаляем сессию
                pipe.delete(session_key)
                # Удаляем токен из set активных сессий пользователя
                pipe.srem(user_sessions_key, token)
                
                await pipe.execute()
            
            logger.info(f"Сессия с токеном {token} успешно деактивирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при деактивации сессии: {e}")
            return False
    
    async def deactivate_all_sessions(self, user_id: int) -> int:
        """
        Деактивирует все активные сессии пользователя.
        Возвращает количество деактивированных сессий.
        """
        logger.info(f"Деактивация всех сессий пользователя {user_id}")
        
        try:
            user_sessions_key = self._get_user_sessions_key(user_id)
            
            # Получаем все активные токены пользователя
            active_tokens = await self.redis.smembers(user_sessions_key)
            
            if not active_tokens:
                logger.info(f"У пользователя {user_id} нет активных сессий")
                return 0
            
            # Деактивируем все сессии
            deactivated_count = 0
            async with self.redis.pipeline() as pipe:
                for token in active_tokens:
                    session_key = self._get_session_key(token)
                    pipe.delete(session_key)
                    deactivated_count += 1
                
                # Очищаем set активных сессий пользователя
                pipe.delete(user_sessions_key)
                
                await pipe.execute()
            
            logger.info(f"Все сессии пользователя {user_id} успешно деактивированы ({deactivated_count} сессий)")
            return deactivated_count
            
        except Exception as e:
            logger.error(f"Ошибка при деактивации всех сессий пользователя {user_id}: {e}")
            return 0
    
    async def get_user_sessions(self, user_id: int) -> Set[str]:
        """
        Получает все активные токены сессий пользователя.
        """
        try:
            user_sessions_key = self._get_user_sessions_key(user_id)
            tokens = await self.redis.smembers(user_sessions_key)
            return set(tokens) if tokens else set()
        except Exception as e:
            logger.error(f"Ошибка при получении сессий пользователя {user_id}: {e}")
            return set()
    
    async def get_session_count(self) -> int:
        """
        Получает общее количество активных сессий.
        """
        try:
            session_keys = await self.redis.keys(f"{self.session_prefix}*")
            return len(session_keys)
        except Exception as e:
            logger.error(f"Ошибка при подсчете сессий: {e}")
            return 0
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Очищает истекшие сессии (Redis делает это автоматически через TTL,
        но эта функция может быть полезна для принудительной очистки).
        """
        try:
            cleaned_count = 0
            session_keys = await self.redis.keys(f"{self.session_prefix}*")
            
            for session_key in session_keys:
                session_data = await self.redis.hgetall(session_key)
                if session_data:
                    token = session_key.split(':', 1)[1]
                    try:
                        session = RedisSession.from_dict(token, session_data)
                        if session.is_expired():
                            await self.deactivate_session(token)
                            cleaned_count += 1
                    except Exception:
                        # Если не можем распарсить сессию, удаляем её
                        await self.redis.delete(session_key)
                        cleaned_count += 1
            
            logger.info(f"Очищено {cleaned_count} истекших сессий")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Ошибка при очистке истекших сессий: {e}")
            return 0

    async def clear_all_sessions(self) -> int:
        """
        Удаляет все сессии из Redis (для тестирования).
        Возвращает количество удаленных сессий.
        """
        logger.info("Удаление всех сессий из Redis")
        try:
            # Получаем все ключи сессий
            session_keys = await self.redis.keys(f"{self.session_prefix}*")
            user_sessions_keys = await self.redis.keys(f"{self.user_sessions_prefix}*")
            
            total_deleted = 0
            
            # Удаляем все сессии
            if session_keys:
                await self.redis.delete(*session_keys)
                total_deleted += len(session_keys)
                logger.info(f"Удалено {len(session_keys)} сессий")
            
            # Удаляем все наборы пользовательских сессий
            if user_sessions_keys:
                await self.redis.delete(*user_sessions_keys)
                total_deleted += len(user_sessions_keys)
                logger.info(f"Удалено {len(user_sessions_keys)} наборов пользовательских сессий")
            
            logger.info(f"Все сессии очищены из Redis. Всего удалено: {total_deleted}")
            return total_deleted
            
        except Exception as e:
            logger.error(f"Ошибка при удалении всех сессий из Redis: {e}")
            return 0


# Глобальный экземпляр сервиса (будет инициализирован в main.py)
redis_session_service: Optional[RedisSessionService] = None


async def get_redis_session_service() -> RedisSessionService:
    """
    Dependency для получения Redis session service.
    """
    if redis_session_service is None:
        raise RuntimeError("Redis session service not initialized")
    return redis_session_service


async def init_redis_session_service(redis_broker: RedisBroker) -> RedisSessionService:
    """
    Инициализация Redis session service.
    """
    global redis_session_service
    redis_session_service = RedisSessionService(redis_broker)
    return redis_session_service 