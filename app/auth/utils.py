from datetime import datetime, timedelta, timezone
from fastapi.responses import Response
from app.auth.models import Session
import secrets
from app.config import SESSION_EXPIRE_SECONDS
from uuid import uuid4
import segno
import contextlib
import io
from functools import lru_cache

def set_tokens(response: Response, session_token: str):
    """
    Устанавливает токен сессии в cookies HTTP-ответа.

    Args:
        response (Response): Объект HTTP-ответа FastAPI.
        session_token (str): Токен сессии для установки в cookies.
    """
    # Устанавливаем основные cookie с менее строгими настройками для совместимости
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,  # Для локальной разработки
        samesite="lax",  # Более совместимая настройка
        max_age=int(SESSION_EXPIRE_SECONDS),  # Срок действия сессии
        path="/",  # Доступно для всех путей
    )
    
    # Добавляем альтернативную cookie с параметрами для Chrome/Firefox
    response.set_cookie(
        key="session_token_alt",
        value=session_token,
        httponly=True,
        secure=False,
        samesite="strict",  # Более строгая настройка для безопасности
        max_age=int(SESSION_EXPIRE_SECONDS),
        path="/",
    )
    
    # Добавляем заголовок для предотвращения кеширования страниц с аутентификацией
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

async def create_session(user_id: int) -> Session:
    """Создание новой сессии"""

    token = secrets.token_urlsafe(32)  # Генерация случайного токена
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_EXPIRE_SECONDS)  # Срок действия сессии

    session = Session(user_id=user_id, token=token, expires_at=expires_at, is_active=True)

    return session


@lru_cache(maxsize=1)
def generate_qr_code(link, error='L'):
    """
    Генерирует QR-код по ссылке с использованием библиотеки segno.

    :param link: Ссылка для кодирования в QR-код
    :param error: Уровень коррекции ошибок (по умолчанию 'L')
    :return: Изображение QR-кода
    """
    qr = segno.make(link, error=error)
    return qr

def generate_deep_link(name):
    token = str(uuid4().hex[:8])  # Генерация укороченного уникального токена
    return f"https://t.me/{name}?start={token}"

def generate_qr_image(link):
    """
    Генерирует QR-код на лету и возвращает его в виде байтов.

    :param link: Ссылка для кодирования в QR-код
    :return: Байты изображения QR-кода
    """
    qr_img = generate_qr_code(link)
    with contextlib.closing(io.BytesIO()) as img_byte_arr:
        qr_img.save(img_byte_arr, kind='png', scale=5, border=1)
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()
