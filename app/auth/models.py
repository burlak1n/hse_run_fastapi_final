from datetime import datetime, timezone
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base, str_uniq, int_uniq, BaseNoID
from app.quest.models import Attempt, Block, QuestionInsider

class Role(Base):
    # "guest" "organizer" "insider" 
    name: Mapped[str_uniq]
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"

class RoleUserCommand(Base):
    # "member", "captain"
    name: Mapped[str_uniq]

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


class User(Base):
    full_name: Mapped[str]
    telegram_id: Mapped[int_uniq] = mapped_column(index=True)
    telegram_username: Mapped[str]

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

    def __repr__(self):
        return f"Ваш профиль:\nФИО: {self.full_name}\ntelegram_id: {self.telegram_id}\ntelegram_username: {self.telegram_username}"


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
        return f"{self.__class__.__name__}(command_id={self.command_id}, user_id={self.user_id}, role_id={self.role_id})"


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
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"
