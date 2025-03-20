from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base, str_uniq, int_uniq

class Language(Base):
    """Модель для языков программирования"""
    name: Mapped[str_uniq]  # Уникальное название языка
    
    # Связь с блоками
    blocks: Mapped[list["Block"]] = relationship("Block", back_populates="language")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"

class Block(Base):
    """Модель для блоков квеста"""
    title: Mapped[str]  # Название блока
    
    # Связь с языком программирования
    language_id: Mapped[int] = mapped_column(ForeignKey('languages.id'), nullable=False, default=1)
    language: Mapped["Language"] = relationship("Language", back_populates="blocks")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, title={self.title}, language_id={self.language_id})"
