from sqladmin import ModelView
from app.auth.models import User, Role

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.full_name, User.telegram_id, User.telegram_username, User.role_id]

class RoleAdmin(ModelView, model=Role):
    column_list = [Role.id, Role.name]
