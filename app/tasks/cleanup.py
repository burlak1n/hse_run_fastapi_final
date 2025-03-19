from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.dao.database import SessionLocal
from app.auth.models import Session

def cleanup_expired_sessions():
    """Удаление истёкших сессий из базы данных."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        db.query(Session).filter(Session.expires_at < now).delete()
        db.commit()
    finally:
        db.close()
