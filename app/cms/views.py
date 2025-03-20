from sqladmin import ModelView
from app.auth.models import Event, User, Role, Command, Language
from app.quest.models import Block

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

class EventAdmin(ModelView, model=Event):
    column_list = [
        Event.id,
        Event.name,
        Event.commands,
        Event.created_at,
        Event.updated_at
    ]
    form_columns = [Event.name, Event.commands]


class CommandAdmin(ModelView, model=Command):
    column_list = [Command.id, Command.name, Command.users]
    form_columns = [Command.name, Command.users]

class BlockAdmin(ModelView, model=Block):
    column_list = [Block.id, Block.title, Block.language]
    form_columns = [Block.title, Block.language]
    
class LanguageAdmin(ModelView, model=Language):
    column_list = [
        Language.id,
        Language.name,
        Language.blocks
    ]
    form_columns = [Language.name]
