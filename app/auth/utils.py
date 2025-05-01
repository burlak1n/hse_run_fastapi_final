import secrets
import hashlib
import hmac
import io
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional
from uuid import uuid4
from base64 import b64encode

from fastapi import Response
from PIL import Image
import segno

from app.auth.models import Session, CommandsUser, User
from app.config import settings

def verify_telegram_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Проверяет данные инициализации Telegram Web App."""
    try:
        # Разделяем строку на пары ключ=значение
        params = dict(item.split("=") for item in init_data.split("&"))
        # Извлекаем хеш для проверки
        received_hash = params.pop("hash")
        
        # Формируем строку данных для проверки хеша
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        
        # Генерируем секретный ключ
        secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        
        # Вычисляем хеш
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # Сравниваем хеши
        if calculated_hash == received_hash:
            # Данные валидны, извлекаем user
            user_data = json.loads(params.get('user', '{}'))
            return user_data
        else:
            # Данные невалидны
            return None
    except Exception as e:
        # Ошибка при разборе или проверке
        # Можно добавить логирование ошибки для отладки
        # logger.error(f"Failed to verify Telegram data: {e}", exc_info=True)
        return None

def set_tokens(response: Response, session_token: str):
    """Устанавливает сессионный токен в httpOnly cookie и дублирует его
       в обычную cookie для доступа из JavaScript.
    """
    expire_seconds = settings.SESSION_EXPIRE_SECONDS
    expires = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
    
    # TODO: Установить secure=True, если приложение работает через HTTPS
    # secure_flag = settings.ENVIRONMENT == "production" # Пример, если есть настройка окружения
    secure_flag = settings.DEBUG # Пока оставляем False для локальной разработки
    
    # Основной httpOnly токен
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax", 
        secure=secure_flag, 
        max_age=expire_seconds,
        expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
    )
    # Альтернативный токен для JS
    response.set_cookie(
        key="session_token_alt",
        value=session_token,
        httponly=False,
        samesite="lax",
        secure=secure_flag,
        max_age=expire_seconds,
        expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
    )
    
    # Добавляем заголовок для предотвращения кеширования страниц с аутентификацией
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

async def create_session(user_id: int) -> Session:
    """Создание новой сессии (асинхронная обертка)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_EXPIRE_SECONDS)
    return Session(user_id=user_id, token=token, expires_at=expires_at, is_active=True)

def generate_qr_image(data: str) -> bytes:
    """Генерирует QR-код с заданными данными и возвращает его в виде байтов PNG."""
    # Создаем QR напрямую здесь
    qr = segno.make(data, error='l') # Используем высокий уровень коррекции ошибок
    
    buffer = io.BytesIO()
    # Параметры отрисовки можно вынести в константы или конфиг при необходимости
    qr.save(buffer, kind='png', scale=5, border=1) 
    buffer.seek(0)
    return buffer.getvalue()

def get_user_role_in_command(command_users: List[CommandsUser], user_id: int) -> Tuple[Optional[str], bool]:
    """
    Проверяет роль пользователя в команде.
    
    Args:
        command_users: Список объектов CommandsUser (связь с загруженными ролями).
        user_id: ID пользователя для проверки.
        
    Returns:
        role_name: Название роли пользователя или None, если пользователь не найден.
        is_captain: True, если пользователь - капитан, False в противном случае.
    """
    user_role_name: Optional[str] = None # Явно указываем тип
    is_captain: bool = False
    for cu in command_users:
        if cu.user_id == user_id:
            # Проверяем наличие роли перед доступом к name
            if cu.role:
                user_role_name = cu.role.name
                if user_role_name == "captain":
                    is_captain = True
            break # Пользователь найден, выходим из цикла
    return user_role_name, is_captain

def format_participants(command_users: List[CommandsUser], include_role: bool = True) -> List[Dict[str, Any]]:
    """
    Форматирует список участников команды, помещая капитана в начало списка.
    
    Args:
        command_users: Список объектов CommandsUser (связь с загруженными пользователями и ролями).
        include_role: Включать ли информацию о роли пользователя в команде.
        
    Returns:
        Отформатированный список участников с капитаном в начале.
    """
    participants = []
    captain_info = None
    
    for cu in command_users:
        # Пропускаем, если нет пользователя или роли (для безопасности)
        if not cu.user or not cu.role:
            continue
            
        participant_data = {
            "id": cu.user.id,
            "full_name": cu.user.full_name,
            "telegram_username": cu.user.telegram_username # Всегда добавляем, если есть
        }
        
        if include_role:
            participant_data["role"] = cu.role.name
            
        # Добавляем информацию об инсайдере/СтС, если применимо
        user_role_name = cu.user.role.name if cu.user.role else None
        if user_role_name == "insider" and cu.user.insider_info:
             participant_data["insider_info"] = {
                 "student_organization": cu.user.insider_info.student_organization,
                 "geo_link": cu.user.insider_info.geo_link
             }
        elif user_role_name == "ctc": 
             insider_info = cu.user.insider_info # Проверяем наличие insider_info
             participant_data["insider_info"] = {
                 "student_organization": "СтС",
                 # Добавляем geo_link только если insider_info существует
                 "geo_link": insider_info.geo_link if insider_info else None 
             }
             
        # Определяем капитана
        if cu.role.name == "captain":
            captain_info = participant_data
        else:
            participants.append(participant_data)
    
    # Сортируем остальных участников по имени для консистентного порядка
    participants.sort(key=lambda p: p['full_name'])
    
    # Ставим капитана в начало списка, если он есть
    if captain_info:
        participants.insert(0, captain_info)
        
    return participants

# Cache Key Builder for User Profile
def user_profile_key_builder(func, *args, **kwargs) -> str:
    """Generates a cache key for user profile data based on user ID."""
    # Assumes the decorated function is called with user_id as the first argument
    # or has user object with an 'id' attribute.
    # Example usage: @cache(key_builder=user_profile_key_builder)
    
    user_dependency_index = -1 # Check if user object is passed via Depends
    try:
        for i, arg in enumerate(args):
             if isinstance(arg, User):
                 user_dependency_index = i
                 break
        # Also check kwargs if necessary, though less common for Depends
    except ImportError:
         pass # User model might not be available here

    if user_dependency_index != -1:
        user_id = args[user_dependency_index].id
    elif 'user_id' in kwargs:
         user_id = kwargs['user_id']
    elif args and isinstance(args[0], int):
         # Simplistic assumption: first integer arg is user_id
         # Make this more robust if needed
         user_id = args[0]
    else:
         # Cannot determine user_id, fallback or raise error
         # Using function name as fallback - less ideal
         # Consider raising an error if user_id is mandatory for the key
         prefix = f"{func.__module__}:{func.__name__}"
         return f"{prefix}:{args}:{kwargs}" # Default-like key

    return f"user_profile:{user_id}"
