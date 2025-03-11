from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
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

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"

class Command(Base):
    name: Mapped[str]
    captain_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    captain: Mapped["User"] = relationship("User", back_populates="commands", lazy="joined")

    count_users: Mapped[int] = mapped_column(default=1, )

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"


class CommandUser(Base):
    command_id: Mapped[int] = mapped_column(ForeignKey('commands.id'), nullable=False)
    command: Mapped["Command"] = relationship("Command", back_populates="users", lazy="joined")

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="commands", lazy="joined")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id})"
