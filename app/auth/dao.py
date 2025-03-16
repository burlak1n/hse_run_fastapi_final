from app.dao.base import BaseDAO
from app.auth.models import User, CommandsUser

class UsersDAO(BaseDAO):
    model = User

class CommandsUsersDAO(BaseDAO):
    model = CommandsUser

# class RoleDAO(BaseDAO):
#     model = Role
