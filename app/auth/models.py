from sqlalchemy import text, ForeignKey, event
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from app.dao.database import Base, str_uniq, int_uniq


class Role(Base):
    # "guest" "organizer" "insider" 
    name: Mapped[str_uniq]
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


class User(Base):
    full_name: Mapped[str]
    telegram_id: Mapped[int_uniq]
    telegram_username: Mapped[str]

    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), default=1, server_default=text("1"))
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")

    # Связь с командами, где пользователь является капитаном
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="captain", lazy="joined")

    # Связь с командами, где пользователь является участником
    command_users: Mapped[list["CommandUser"]] = relationship("CommandUser", back_populates="user", lazy="joined")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"


class Command(Base):
    name: Mapped[str]
    captain_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    captain: Mapped["User"] = relationship("User", back_populates="commands", lazy="joined")

    count_users: Mapped[int] = mapped_column(default=1, nullable=False)

    # Связь с участниками команды
    command_users: Mapped[list["CommandUser"]] = relationship("CommandUser", back_populates="command", lazy="joined")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"


class CommandUser(Base):
    command_id: Mapped[int] = mapped_column(ForeignKey('commands.id'), nullable=False)
    command: Mapped["Command"] = relationship("Command", back_populates="command_users", lazy="joined")

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="command_users", lazy="joined")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"



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
