from sqladmin import ModelView
from app.auth.models import Event, User, Role, Command, Language, RoleUserCommand
from app.quest.models import Answer, Block, Question, AttemptType, Attempt
from sqladmin.forms import FileField
from fastapi import UploadFile, Request
from app.logger import logger
from typing import Any
import os
from pathlib import Path
from markupsafe import Markup

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
    form_columns = [Event.name]


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
    
class RoleUserCommandAdmin(ModelView, model=RoleUserCommand):
    column_list = [
        RoleUserCommand.id,
        RoleUserCommand.name
    ]
    form_columns = [RoleUserCommand.name]

class QuestionAdmin(ModelView, model=Question):
    column_list = [
        Question.id,
        Question.title,
        Question.block,
        Question.image_path,
        Question.geo_answered,
        Question.text_answered,
        Question.image_path_answered
    ]

    form_columns = [
        Question.title,
        Question.block,
        Question.image_path,
        Question.geo_answered,
        Question.text_answered,
        Question.image_path_answered
    ]
    form_overrides = {
        'image_path': FileField,
        'image_path_answered': FileField
    }

    def format_image_url(model, attribute) -> Markup:
        image_path = getattr(model, attribute)
        if image_path:
            return Markup(f'<img src="/static/img/{image_path}" style="max-width: 200px; max-height: 200px;" />')
        return Markup('')

    def format_block_link(model, attribute) -> Markup:
        block = getattr(model, attribute)
        if block:
            return Markup(f'<a href="/cms/block/details/{block.id}">{block.title}</a>')
        return Markup('')

    column_formatters = {
        "block": format_block_link,
        "image_path": format_image_url,
        "image_path_answered": format_image_url,
    }
    column_formatters_detail = {
        "block": format_block_link,
        "image_path": format_image_url,
        "image_path_answered": format_image_url,
    }

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        if 'image_path' in data:
            file = data['image_path']
            if hasattr(file, 'filename') and hasattr(file, 'read'):
                # Удаляем старый файл, если он существует
                if model.image_path:
                    old_file_path = Path("app/static/img") / model.image_path
                    if old_file_path.exists():
                        os.remove(old_file_path)
                
                file_content = await file.read()
                file_path = Path("app/static/img") / file.filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                # Сохраняем только имя файла в базу данных
                data['image_path'] = file.filename
            else:
                data['image_path'] = file

        if 'image_path_answered' in data:
            file = data['image_path_answered']
            if hasattr(file, 'filename') and hasattr(file, 'read'):
                # Удаляем старый файл, если он существует
                if model.image_path_answered:
                    old_file_path = Path("app/static/img") / model.image_path_answered
                    if old_file_path.exists():
                        os.remove(old_file_path)
                
                file_content = await file.read()
                file_path = Path("app/static/img") / file.filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                # Сохраняем только имя файла в базу данных
                data['image_path_answered'] = file.filename
            else:
                data['image_path_answered'] = file

        return await super().on_model_change(data, model, is_created, request)


    async def on_model_delete(self, model: Any, request: Request) -> None:
        # Удаляем файл image_path, если он существует
        if model.image_path:
            file_path = Path("app/static/img") / model.image_path
            if file_path.exists():
                os.remove(file_path)

        # Удаляем файл image_path_answered, если он существует
        if model.image_path_answered:
            file_path = Path("app/static/img") / model.image_path_answered
            if file_path.exists():
                os.remove(file_path)

        return await super().on_model_delete(model, request)

class AnswerAdmin(ModelView, model=Answer):
    column_list = [
        Answer.id,
        Answer.answer_text,
        Answer.question
    ]
    form_columns = [
        Answer.answer_text,
        Answer.question,
    ]

    def format_question_link(model, attribute) -> Markup:
        question = getattr(model, attribute)
        if question:
            return Markup(f'<a href="/cms/question/details/{question.id}">{question.title}</a>')
        return Markup('')

    column_formatters = {
        "question": format_question_link,
    }
    column_formatters_detail = {
        "question": format_question_link,
    }

class AttemptTypeAdmin(ModelView, model=AttemptType):
    column_list = [
        AttemptType.id,
        AttemptType.name,
        AttemptType.score,
        AttemptType.money,
        AttemptType.is_active
    ]
    form_columns = [
        AttemptType.name,
        AttemptType.score,
        AttemptType.money,
        AttemptType.is_active
    ]

class AttemptAdmin(ModelView, model=Attempt):
    column_list = [
        Attempt.id,
        Attempt.command,
        Attempt.user,
        Attempt.question,
        Attempt.attempt_type,
        Attempt.attempt_text,
        Attempt.is_true,
        Attempt.created_at
    ]
    form_columns = [
        Attempt.command,
        Attempt.user,
        Attempt.question,
        Attempt.attempt_type,
        Attempt.attempt_text,
        Attempt.is_true
    ]

    def format_command_link(model, attribute) -> Markup:
        command = getattr(model, attribute)
        if command:
            return Markup(f'<a href="/cms/command/details/{command.id}">{command.name}</a>')
        return Markup('')

    def format_user_link(model, attribute) -> Markup:
        user = getattr(model, attribute)
        if user:
            return Markup(f'<a href="/cms/user/details/{user.id}">{user.full_name}</a>')
        return Markup('')

    def format_question_link(model, attribute) -> Markup:
        question = getattr(model, attribute)
        if question:
            return Markup(f'<a href="/cms/question/details/{question.id}">{question.title}</a>')
        return Markup('')

    def format_attempt_type_link(model, attribute) -> Markup:
        attempt_type = getattr(model, attribute)
        if attempt_type:
            return Markup(f'<a href="/cms/attempttype/details/{attempt_type.id}">{attempt_type.name}</a>')
        return Markup('')

    column_formatters = {
        "command": format_command_link,
        "user": format_user_link,
        "question": format_question_link,
        "attempt_type": format_attempt_type_link
    }
    column_formatters_detail = {
        "command": format_command_link,
        "user": format_user_link,
        "question": format_question_link,
        "attempt_type": format_attempt_type_link
    }
