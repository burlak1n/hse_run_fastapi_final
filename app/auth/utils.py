from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from fastapi.responses import Response
from app.config import settings
import secrets
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet


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


async def authenticate_user(db: Session, user, password):
    if not user or verify_password(plain_password=password, hashed_password=user.password) is False:
        return None
    return user


def set_tokens(response: Response, db: Session, user_id: int):
    """Установка токена сессии в куки"""
    token = create_session(db, user_id)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax"
    )


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_session(db: Session, user_id: int) -> str:
    """Создание новой сессии"""
    token = secrets.token_urlsafe(32)  # Генерация случайного токена
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # Срок действия сессии

    session = Session(user_id=user_id, token=token, expires_at=expires_at)
    db.add(session)
    db.commit()
    db.refresh(session)

    return token

def get_session(db: Session, token: str):
    """Получение сессии по токену"""
    session = db.query(Session).filter(Session.token == token).first()
    if not session or session.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token"
        )
    return session

def delete_session(db: Session, token: str):
    """Удаление сессии"""
    session = db.query(Session).filter(Session.token == token).first()
    if session:
        db.delete(session)
        db.commit()

def revoke_all_sessions(db: Session, user_id: int):
    """Отзыв всех сессий пользователя."""
    db.query(Session).filter(Session.user_id == user_id).update({"is_revoked": True})
    db.commit()

key = Fernet.generate_key()
cipher_suite = Fernet(key)

def encrypt_token(token: str) -> str:
    return cipher_suite.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    return cipher_suite.decrypt(encrypted_token.encode()).decode()
