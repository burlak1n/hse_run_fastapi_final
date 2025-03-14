from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.dao.database import Base, str_uniq, int_uniq
from datetime import datetime, timezone

# class Role(Base):
#     # "guest" "organizer" "insider" 
#     name: Mapped[str_uniq]
#     users: Mapped[list["User"]] = relationship(back_populates="role")

#     def __repr__(self):
#         return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


class User(Base):
    full_name: Mapped[str]
    telegram_id: Mapped[int_uniq]
    telegram_username: Mapped[str]

    # role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), default=1, server_default=text("1"))
    # role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")

    # Связь с командами, где пользователь является капитаном
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="captain", lazy="joined")

    # Связь с командами, где пользователь является участником
    # command_users: Mapped[list["CommandUser"]] = relationship("CommandUser", back_populates="user", lazy="joined")

    def __repr__(self):
        return f"ФИО: {self.full_name}\ntelegram_id: {self.telegram_id}\ntelegram_username: {self.telegram_username}"


class Command(Base):
    name: Mapped[str]
    captain_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    captain: Mapped["User"] = relationship("User", back_populates="commands", lazy="joined")

    count_users: Mapped[int] = mapped_column(default=1, nullable=False)

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


# class CommandUser(Base):
#     command_id: Mapped[int] = mapped_column(ForeignKey('commands.id'), nullable=False)
#     command: Mapped["Command"] = relationship("Command", back_populates="command_users", lazy="joined")

#     user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
#     user: Mapped["User"] = relationship("User", back_populates="command_users", lazy="joined")


class Session(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    token: Mapped[str] = mapped_column(nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    user_agent: Mapped[str] = mapped_column(nullable=True)  # Весь User-Agent
    is_revoked: Mapped[bool] = mapped_column(default=False)
    last_activity: Mapped[datetime] = mapped_column(nullable=True)

    def is_expired(self) -> bool:
        """Проверка, истёк ли срок действия сессии."""
        return datetime.now(timezone.utc) > self.expires_at

    def revoke(self):
        """Отзыв сессии."""
        self.is_revoked = True

    def is_valid(self) -> bool:
        """Проверка, действительна ли сессия."""
        return not self.is_expired() and not self.is_revoked

    def update_last_activity(self):
        """Обновляет время последней активности до текущего времени."""
        self.last_activity = datetime.now(timezone.utc)

# @event.listens_for(User, 'after_update')
# def update_user_in_commands(mapper, connection, target):
#     # target - это объект User, который был обновлен
#     session = Session(bind=connection)

#     # Проверяем, изменилась ли роль пользователя
#     if target.role_id == 2:  # Например, если роль пользователя "участник команды"
#         # Проверяем, есть ли уже запись в CommandUsers
#         existing = session.query(CommandUser).filter_by(user_id=target.id, command_id=1).first()
#         if not existing:
#             # Создаем запись в CommandUsers
#             command_user = CommandUser(command_id=1, user_id=target.id)
#             session.add(command_user)
#             session.commit()
