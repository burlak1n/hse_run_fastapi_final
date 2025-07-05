"""
Админ-панель для управления Redis сессиями.
Предоставляет web-интерфейс для мониторинга и управления активными сессиями.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select


from app.auth.redis_session import get_redis_session_service, RedisSession
from app.auth.models import User
from app.dao.database import async_session_maker
from app.config import settings
from app.logger import logger


class RedisSessionAdmin:
    """Админ-класс для управления Redis сессиями"""
    
    def __init__(self):
        self.name = "Redis Sessions"
        self.icon = "fa-solid fa-server"
        
    async def get_sessions_list(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Получить список активных сессий с пагинацией"""
        if not settings.USE_REDIS:
            return {"sessions": [], "total": 0, "page": page, "per_page": per_page}
            
        try:
            redis_session_service = await get_redis_session_service()
            
            # Получаем все ключи сессий
            session_keys = await redis_session_service.redis.keys(f"{redis_session_service.session_prefix}*")
            total = len(session_keys)
            
            # Применяем пагинацию
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_keys = session_keys[start_idx:end_idx]
            
            sessions = []
            
            # Получаем информацию о пользователях
            async with async_session_maker() as db_session:
                for session_key in paginated_keys:
                    try:
                        token = session_key.split(':', 1)[1]
                        session_data = await redis_session_service.redis.hgetall(session_key)
                        
                        if session_data:
                            redis_session = RedisSession.from_dict(token, session_data)
                            
                            # Получаем информацию о пользователе
                            user_query = select(User).where(User.id == redis_session.user_id)
                            user_result = await db_session.execute(user_query)
                            user = user_result.scalar_one_or_none()
                            
                            sessions.append({
                                "token": redis_session.token,
                                "user_id": redis_session.user_id,
                                "user_name": user.full_name if user else "Unknown",
                                "user_telegram": user.telegram_username if user else None,
                                "expires_at": redis_session.expires_at,
                                "is_active": redis_session.is_active,
                                "is_expired": redis_session.is_expired(),
                                "is_valid": redis_session.is_valid(),
                                "ttl_seconds": await redis_session_service.redis.ttl(session_key)
                            })
                    except Exception as e:
                        logger.error(f"Ошибка получения данных сессии {session_key}: {e}")
                        continue
            
            return {
                "sessions": sessions,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения списка сессий: {e}")
            return {"sessions": [], "total": 0, "page": page, "per_page": per_page}
    
    async def get_session_details(self, token: str) -> Optional[Dict[str, Any]]:
        """Получить детальную информацию о сессии"""
        if not settings.USE_REDIS:
            return None
            
        try:
            redis_session_service = await get_redis_session_service()
            session = await redis_session_service.get_session(token)
            
            if not session:
                return None
            
            # Получаем информацию о пользователе
            async with async_session_maker() as db_session:
                user_query = select(User).where(User.id == session.user_id)
                user_result = await db_session.execute(user_query)
                user = user_result.scalar_one_or_none()
                
                session_key = redis_session_service._get_session_key(token)
                user_sessions_key = redis_session_service._get_user_sessions_key(session.user_id)
                
                return {
                    "token": session.token,
                    "user_id": session.user_id,
                    "user_name": user.full_name if user else "Unknown",
                    "user_telegram": user.telegram_username if user else None,
                    "user_role": user.role.name if user and user.role else None,
                    "expires_at": session.expires_at,
                    "is_active": session.is_active,
                    "is_expired": session.is_expired(),
                    "is_valid": session.is_valid(),
                    "ttl_seconds": await redis_session_service.redis.ttl(session_key),
                    "user_sessions_count": await redis_session_service.redis.scard(user_sessions_key)
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения детализации сессии {token}: {e}")
            return None
    
    async def revoke_session(self, token: str) -> bool:
        """Отозвать сессию"""
        if not settings.USE_REDIS:
            return False
            
        try:
            redis_session_service = await get_redis_session_service()
            return await redis_session_service.deactivate_session(token)
        except Exception as e:
            logger.error(f"Ошибка отзыва сессии {token}: {e}")
            return False
    
    async def revoke_user_sessions(self, user_id: int) -> int:
        """Отозвать все сессии пользователя"""
        if not settings.USE_REDIS:
            return 0
            
        try:
            redis_session_service = await get_redis_session_service()
            return await redis_session_service.deactivate_all_sessions(user_id)
        except Exception as e:
            logger.error(f"Ошибка отзыва сессий пользователя {user_id}: {e}")
            return 0
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику по сессиям"""
        if not settings.USE_REDIS:
            return {"total_sessions": 0, "active_sessions": 0, "expired_sessions": 0}
            
        try:
            redis_session_service = await get_redis_session_service()
            
            # Получаем все сессии
            session_keys = await redis_session_service.redis.keys(f"{redis_session_service.session_prefix}*")
            total_sessions = len(session_keys)
            
            active_sessions = 0
            expired_sessions = 0
            users_with_sessions = set()
            
            for session_key in session_keys:
                try:
                    token = session_key.split(':', 1)[1]
                    session_data = await redis_session_service.redis.hgetall(session_key)
                    
                    if session_data:
                        redis_session = RedisSession.from_dict(token, session_data)
                        users_with_sessions.add(redis_session.user_id)
                        
                        if redis_session.is_valid():
                            active_sessions += 1
                        else:
                            expired_sessions += 1
                            
                except Exception as e:
                    logger.error(f"Ошибка анализа сессии {session_key}: {e}")
                    continue
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "unique_users": len(users_with_sessions)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {"total_sessions": 0, "active_sessions": 0, "expired_sessions": 0, "unique_users": 0}
    
    async def cleanup_expired_sessions(self) -> int:
        """Очистить истекшие сессии"""
        if not settings.USE_REDIS:
            return 0
            
        try:
            redis_session_service = await get_redis_session_service()
            return await redis_session_service.cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Ошибка очистки истекших сессий: {e}")
            return 0

    async def clear_all_sessions(self) -> int:
        """Удалить все сессии (для тестирования Redis)"""
        if not settings.USE_REDIS:
            return 0
            
        try:
            redis_session_service = await get_redis_session_service()
            return await redis_session_service.clear_all_sessions()
        except Exception as e:
            logger.error(f"Ошибка при удалении всех сессий: {e}")
            return 0


# Глобальный экземпляр админ-класса
redis_session_admin = RedisSessionAdmin() 