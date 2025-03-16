from sqlalchemy import text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base, str_uniq, int_uniq, BaseNoID

class Role(Base):
    # "guest" "organizer" "insider" 
    name: Mapped[str_uniq]
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"

class RoleUserCommand(Base):
    # "member", "captain", etc.
    name: Mapped[str_uniq]

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


class User(Base):
    full_name: Mapped[str]
    telegram_id: Mapped[int_uniq] = mapped_column(index=True)
    telegram_username: Mapped[str]

    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), default=1, server_default=text("1"))
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")

    # Команды, где пользователь участник или капитан
    commands_association: Mapped[list["CommandsUser"]] = relationship("CommandsUser", back_populates="user")

    def __repr__(self):
        return f"Ваш профиль:\nФИО: {self.full_name}\ntelegram_id: {self.telegram_id}\ntelegram_username: {self.telegram_username}"


class Command(Base):
    name: Mapped[str]

    # Участники команды (включая капитана)
    users_association: Mapped[list["CommandsUser"]] = relationship("CommandsUser", back_populates="command")

    # Связь с мероприятием
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), nullable=False)
    event: Mapped["Event"] = relationship("Event", back_populates="commands")
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
    command: Mapped["Command"] = relationship("Command", back_populates="users_association")
    user: Mapped["User"] = relationship("User", back_populates="commands_association")
    role: Mapped["RoleUserCommand"] = relationship("RoleUserCommand")


# class Session(Base):
#     user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
#     token: Mapped[str] = mapped_column(nullable=False, unique=True)
#     expires_at: Mapped[datetime] = mapped_column(nullable=False)
#     user_agent: Mapped[str] = mapped_column(nullable=True)  # Весь User-Agent
#     is_revoked: Mapped[bool] = mapped_column(default=False)
#     last_activity: Mapped[datetime] = mapped_column(nullable=True)

#     def is_expired(self) -> bool:
#         """Проверка, истёк ли срок действия сессии."""
#         return datetime.now(timezone.utc) > self.expires_at

#     def revoke(self):
#         """Отзыв сессии."""
#         self.is_revoked = True

#     def is_valid(self) -> bool:
#         """Проверка, действительна ли сессия."""
#         return not self.is_expired() and not self.is_revoked

#     def update_last_activity(self):
#         """Обновляет время последней активности до текущего времени."""
#         self.last_activity = datetime.now(timezone.utc)
