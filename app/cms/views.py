from sqladmin import ModelView
from app.auth.models import User, Role, Command

class UserAdmin(ModelView, model=User):
    column_list = [
        User.id,
        User.full_name,
        User.telegram_id,
        User.telegram_username,
        User.role,
        User.created_at,
        User.updated_at
    ]
    form_columns = [User.full_name, User.telegram_id, User.telegram_username, User.role_id]

class RoleAdmin(ModelView, model=Role):
    column_list = [Role.id, Role.name]
    form_columns = [Role.name]

class CommandAdmin(ModelView, model=Command):
    column_list = [Command.id, Command.name, Command.users]
    form_columns = [Command.name, Command.users]

