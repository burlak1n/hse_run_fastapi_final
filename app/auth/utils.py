from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from fastapi.responses import Response
from app.auth.models import Session
from app.config import settings
import secrets
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet
from app.config import SESSION_EXPIRE_SECONDS


def create_tokens(data: dict) -> dict:
    # Текущее время в UTC
    now = datetime.now(timezone.utc)

    # AccessToken - 30 минут
    access_expire = now + timedelta(seconds=10)
    access_payload = data.copy()
    access_payload.update({"exp": int(access_expire.timestamp()), "type": "access"})
    access_token = jwt.encode(
        access_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    # RefreshToken - 7 дней
    refresh_expire = now + timedelta(days=7)
    refresh_payload = data.copy()
    refresh_payload.update({"exp": int(refresh_expire.timestamp()), "type": "refresh"})
    refresh_token = jwt.encode(
        refresh_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return {"access_token": access_token, "refresh_token": refresh_token}




def set_tokens(response: Response, session_token: str):
    """
    Устанавливает токен сессии в cookies HTTP-ответа.

    Args:
        response (Response): Объект HTTP-ответа FastAPI.
        db (AsyncSession): Асинхронная сессия для работы с базой данных.
    Raises:
        HTTPException: Если не удалось создать или установить токен.
    """
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,
        # secure=True,
        samesite="lax",
        max_age=int(SESSION_EXPIRE_SECONDS),  # Срок действия 7 дней
    )


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_session(user_id: int) -> Session:
    """Создание новой сессии"""

    token = secrets.token_urlsafe(32)  # Генерация случайного токена
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # Срок действия сессии

    session = Session(user_id=user_id, token=token, expires_at=expires_at, is_active=True)

    return session
