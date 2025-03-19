from datetime import datetime, timedelta, timezone
from fastapi.responses import Response
from app.auth.models import Session
import secrets
from app.config import SESSION_EXPIRE_SECONDS


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

async def create_session(user_id: int) -> Session:
    """Создание новой сессии"""

    token = secrets.token_urlsafe(32)  # Генерация случайного токена
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # Срок действия сессии

    session = Session(user_id=user_id, token=token, expires_at=expires_at, is_active=True)

    return session
