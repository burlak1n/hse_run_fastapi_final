from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base

class Block(Base):
    """Модель для блоков квеста"""
    title: Mapped[str]  # Название блока
    
    # Связь с языком
    language_id: Mapped[int] = mapped_column(ForeignKey('languages.id'), nullable=False, default=1)
    language: Mapped["Language"] = relationship("Language", back_populates="blocks", lazy="joined")  # Используем строку для указания модели

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, title={self.title}, language_id={self.language_id})"
