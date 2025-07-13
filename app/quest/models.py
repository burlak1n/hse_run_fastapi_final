from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base
from typing import Optional

class Block(Base):
    """Модель для блоков квеста"""
    title: Mapped[str]  # Название блока
    
    # Связь с языком
    language_id: Mapped[int] = mapped_column(ForeignKey('languages.id'), nullable=False, default=1)
    language: Mapped["Language"] = relationship("Language", back_populates="blocks", lazy="joined")  # Используем строку для указания модели

    image_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    # Связь с вопросами
    questions: Mapped[list["Question"]] = relationship("Question", back_populates="block")

    def __repr__(self):
        return f"{self.title}"


class Question(Base):
    """Модель для вопросов в блоках квеста"""
    title: Mapped[str]
    block_id: Mapped[int] = mapped_column(ForeignKey('blocks.id'), nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    geo_answered: Mapped[str]
    text_answered: Mapped[str]
    image_path_answered: Mapped[Optional[str]] = mapped_column(nullable=True)
    hint_path: Mapped[Optional[str]] = mapped_column(nullable=True)  # Путь к подсказке

    longread: Mapped[Optional[str]] = mapped_column(nullable=True)  # Лонгрид

    # Связь с блоком
    block: Mapped["Block"] = relationship("Block", back_populates="questions")

    # Добавляем связь с ответами
    answers: Mapped[list["Answer"]] = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    
    # Связь с инсайдерами
    insiders: Mapped[list["QuestionInsider"]] = relationship("QuestionInsider", back_populates="question", cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.title}"


class Answer(Base):
    """Модель для ответов на вопросы"""
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), nullable=False)
    answer_text: Mapped[str]
    additional_field_value: Mapped[Optional[str]] = mapped_column(nullable=True)

    # Связь с вопросом
    question: Mapped["Question"] = relationship("Question", back_populates="answers")

    def __repr__(self):
        return f"Answer(id={self.id}, question_id={self.question_id}, answer_text={self.answer_text})"

class AttemptType(Base):
    """Типы попыток"""
    name: Mapped[str]
    score: Mapped[int]
    money: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)
    def __repr__(self):
        return f"{self.name}"

class Attempt(Base):
    """Попытки / Транзакции пользователей"""
    command_id: Mapped[int] = mapped_column(ForeignKey('commands.id', ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete="CASCADE"))
    question_id: Mapped[Optional[int]] = mapped_column(ForeignKey('questions.id', ondelete="SET NULL"), nullable=True)
    attempt_type_id: Mapped[int] = mapped_column(ForeignKey('attempttypes.id', ondelete="CASCADE"))
    attempt_text: Mapped[Optional[str]]
    is_true: Mapped[bool] = mapped_column(default=False) # Было ли начисление

    # Связи
    command: Mapped["Command"] = relationship("Command")
    user: Mapped["User"] = relationship("User")
    question: Mapped["Question"] = relationship("Question")
    attempt_type: Mapped["AttemptType"] = relationship("AttemptType")
    
class QuestionInsider(Base):
    """Модель для связи вопросов с инсайдерами"""
    __table_args__ = (
        UniqueConstraint('question_id', 'user_id', name='unique_question_insider'),
    )
    
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    
    # Связи
    question: Mapped["Question"] = relationship("Question", back_populates="insiders")
    user: Mapped["User"] = relationship("User", back_populates="insider_questions")
    
    def __repr__(self):
        return f"{self.question_id}"
