from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base
from typing import Optional

class Block(Base):
    """Модель для блоков квеста"""
    title: Mapped[str]  # Название блока
    
    # Связь с языком
    language_id: Mapped[int] = mapped_column(ForeignKey('languages.id'), nullable=False, default=1)
    language: Mapped["Language"] = relationship("Language", back_populates="blocks", lazy="joined")  # Используем строку для указания модели

    # Связь с вопросами
    questions: Mapped[list["Question"]] = relationship("Question", back_populates="block")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, title={self.title}, language_id={self.language_id})"


class Question(Base):
    """Модель для вопросов в блоках квеста"""
    block_id: Mapped[int] = mapped_column(ForeignKey('blocks.id'), nullable=False)
    title: Mapped[str]
    image_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    geo_answered: Mapped[str]
    text_answered: Mapped[str]
    image_path_answered: Mapped[Optional[str]] = mapped_column(nullable=True)

    # Связь с блоком
    block: Mapped["Block"] = relationship("Block", back_populates="questions")

    def __repr__(self):
        return f"Question(id={self.id}, title={self.title}, block_id={self.block_id})"


class Answer(Base):
    """Модель для ответов на вопросы"""
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), nullable=False)
    answer_text: Mapped[str]

    # Связь с вопросом
    # question: Mapped["Question"] = relationship("Question", back_populates="answers")

    def __repr__(self):
        return f"Answer(id={self.id}, question_id={self.question_id}, answer_text={self.answer_text})"
