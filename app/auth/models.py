from datetime import datetime, timezone
import uuid
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base, str_uniq, int_uniq, BaseNoID
from app.quest.models import Attempt, Block, QuestionInsider

class Role(Base):
    # "guest" "organizer" "insider" "ctc"
    name: Mapped[str_uniq]
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self):
        return f"{self.name}"

class RoleUserCommand(Base):
    # "member", "captain"
    name: Mapped[str_uniq]

    def __repr__(self):
        return f"{self.name}"


class User(Base):
    full_name: Mapped[str]
    telegram_id: Mapped[int_uniq] = mapped_column(index=True)
    telegram_username: Mapped[str | None] = mapped_column(nullable=True)
    is_looking_for_friends: Mapped[bool] = mapped_column(default=False)

    # Если нет ролей, то пользователь неактивный
    role_id: Mapped[int | None] = mapped_column(
        ForeignKey('roles.id', ondelete='SET NULL'),
        default=None,
        nullable=True,
        comment='Идентификатор роли пользователя. Если NULL - пользователь неактивен'
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")

    # Команды, где пользователь участник или капитан
    commands: Mapped[list["CommandsUser"]] = relationship("CommandsUser", back_populates="user")
    
    # Вопросы, закрепленные за инсайдером
    insider_questions: Mapped[list["QuestionInsider"]] = relationship("QuestionInsider", back_populates="user")
    
    # Профиль пользователя с дополнительной информацией
    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Информация об инсайдере
    insider_info: Mapped["InsiderInfo"] = relationship("InsiderInfo", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.full_name}"

class UserProfile(Base):
    """Модель для хранения дополнительной информации о пользователе"""
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    email: Mapped[str] = mapped_column(nullable=True)
    # student_organization: Mapped[str] = mapped_column(nullable=True)
    # geo_link: Mapped[str] = mapped_column(nullable=True)
    
    # Обратная связь с пользователем
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"{self.email or 'No email'}"

class InsiderInfo(Base):
    """Модель для хранения дополнительной информации об инсайдерах"""
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    student_organization: Mapped[str] = mapped_column(nullable=True)
    geo_link: Mapped[str] = mapped_column(nullable=True)
    
    # Обратная связь с пользователем
    user: Mapped["User"] = relationship("User", back_populates="insider_info")

    def __repr__(self):
        return f"{self.student_organization}"

class Command(Base):
    name: Mapped[str]

    # Участники команды (включая капитана) с cascade delete
    users: Mapped[list["CommandsUser"]] = relationship("CommandsUser", back_populates="command", cascade="all, delete-orphan")

    # Связь с мероприятием
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), nullable=False)
    event: Mapped["Event"] = relationship("Event", back_populates="commands")

    # Связь с языком
    language_id: Mapped[int] = mapped_column(ForeignKey('languages.id'), nullable=False, default=1)
    language: Mapped["Language"] = relationship("Language", back_populates="commands")

    # Связь с попытками
    attempts: Mapped[list["Attempt"]] = relationship("Attempt", back_populates="command", cascade="all, delete-orphan")
    
    # Связь с приглашениями
    invite: Mapped["CommandInvite"] = relationship("CommandInvite", back_populates="command", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return self.name
        participants = []
        for idx, user_assoc in enumerate(self.users, start=1):
            role = user_assoc.role.name if user_assoc.role else ""
            participant_info = f"{idx}. {user_assoc.user.full_name}"
            if role:
                participant_info += f" | {role}"
            participants.append(participant_info)
        participants_str = "\n".join(participants)
        return f"Команда: {self.name} | {len(self.users)}/6\n{participants_str}"
    def __repr__(self):
        return f"{self.name}"

class CommandInvite(Base):
    """Модель для хранения UUID приглашений команд"""
    command_id: Mapped[int] = mapped_column(ForeignKey('commands.id', ondelete='CASCADE'), unique=True)
    invite_uuid: Mapped[str] = mapped_column(unique=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    # Обратная связь с командой
    command: Mapped["Command"] = relationship("Command", back_populates="invite")
    
    def __repr__(self):
        return f"Invite for {self.command.name if self.command else 'Unknown'}"
    # __table_args__ = (
    #     CheckConstraint('count_users >= 1 AND count_users <= 100', name='check_count_users_range'),
    # )

    # @validates('count_users')
    # def validate_count_users(self, key, value):
    #     if not (1 <= value <= 100):  # Пример: минимум 1, максимум 100
    #         raise ValueError("count_users must be between 1 and 100")
    #     return value

    # Связь с участниками команды
    # command_users: Mapped[list["CommandUser"]] = relationship("CommandUser", back_populates="command", lazy="joined")

class Event(Base):
    name: Mapped[str]
    start_time: Mapped[datetime] = mapped_column(nullable=True)
    end_time: Mapped[datetime] = mapped_column(nullable=True)
    # Связь с командами
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="event")

    def __repr__(self):
        return f"{self.name}"

class CommandsUser(BaseNoID):
    __table_args__ = (
        UniqueConstraint('command_id', 'user_id', name='unique_command_user'),
    )

    command_id: Mapped[int] = mapped_column(ForeignKey('commands.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('roleusercommands.id'))  # Ссылка на роль

    # Опционально: связи для удобства доступа
    command: Mapped["Command"] = relationship("Command", back_populates="users")
    user: Mapped["User"] = relationship("User", back_populates="commands")
    role: Mapped["RoleUserCommand"] = relationship("RoleUserCommand")

    def __repr__(self):
        return f"{self.command_id}"


class Session(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    token: Mapped[str] = mapped_column(nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    # user_agent: Mapped[str] = mapped_column(nullable=True)  # Весь User-Agent
    is_active: Mapped[bool] = mapped_column(default=False)

    def is_expired(self) -> bool:
        """Проверка, истёк ли срок действия сессии."""
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    def revoke(self):
        """Отзыв сессии."""
        self.is_active = False

    def is_valid(self) -> bool:
        """Проверка, действительна ли сессия."""
        return not self.is_expired() and self.is_active

    # def update_last_activity(self):
    #     """Обновляет время последней активности до текущего времени."""
    #     self.last_activity = datetime.now(timezone.utc)

class Language(Base):
    """Модель для языков программирования"""
    name: Mapped[str_uniq]  # Уникальное название языка
    
    # Связь с блоками
    blocks: Mapped[list["Block"]] = relationship("Block", back_populates="language", lazy="joined")

    # Связь с командами
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="language", lazy="joined")

    def __repr__(self):
        return f"{self.name}"

class Program(Base):
    """Модель для хранения баллов пользователей (посещения и взаимодействия)"""
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    score: Mapped[float] = mapped_column(default=0)
    comment: Mapped[str | None] = mapped_column(nullable=True)
    
    # Обратная связь с пользователем
    user: Mapped["User"] = relationship("User", backref="program_scores")
    
    def __repr__(self):
        return f"{self.comment}"
