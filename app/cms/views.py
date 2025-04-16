from sqladmin import ModelView
from sqlalchemy import Select
from app.auth.models import Event, User, Role, Command, Language, RoleUserCommand, Session, CommandsUser
from app.quest.models import Answer, Block, Question, AttemptType, Attempt, QuestionInsider
from sqladmin.forms import FileField
from fastapi import UploadFile, Request
from app.logger import logger
from typing import Any
import os
from pathlib import Path
from markupsafe import Markup
import uuid

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
    form_columns = [
        User.full_name, 
        User.telegram_id, 
        User.telegram_username, 
        User.role
    ]
    form_ajax_refs = {
        'role': {
            'fields': ['name'],
            'order_by': 'name',
        }
    }

class RoleAdmin(ModelView, model=Role):
    column_list = [Role.id, Role.name]
    form_columns = [Role.name]
    
class EventAdmin(ModelView, model=Event):
    column_list = [
        Event.id,
        Event.name,
        Event.commands,
        Event.start_time,
        Event.end_time,
        Event.created_at,
        Event.updated_at
    ]
    form_columns = [Event.name, Event.start_time, Event.end_time]


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
        Question.image_path_answered,
        Question.hint_path,
        Question.answers,
    ]

    form_columns = [
        Question.title,
        Question.block,
        Question.image_path,
        Question.geo_answered,
        Question.text_answered,
        Question.image_path_answered,
        Question.hint_path
    ]

    form_overrides = {
        'image_path': FileField,
        'image_path_answered': FileField,
        'hint_path': FileField
    }

    column_sortable_list = [
        Question.id,
        Question.title,
        Question.block,
    ]

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

    def format_hint_link(model, attribute) -> Markup:
        hint_path = getattr(model, attribute)
        if hint_path:
            return Markup(f'<a href="/static/img/{hint_path}" target="_blank">Посмотреть подсказку</a>')
        return Markup('')

    def format_truncated_text(model, attribute) -> Markup:
        full_text = getattr(model, attribute)
        if full_text:
            truncated = full_text[:30] + '...' if len(full_text) > 30 else full_text
            return Markup(f'<span title="{full_text}">{truncated}</span>')
        return Markup('')

    def format_answer_text(model, attribute):
        """Простой вывод текста ответов - по одному символю на ответ."""
        answers = getattr(model, attribute)
        if not answers:
            return ""
        
        # Просто вернем первую букву каждого ответа
        result = ""
        for answer in answers:
            text = getattr(answer, "answer_text", "")
            if text and isinstance(text, str):
                result += text[0]  # Берем только первый символ
        
        return result

    column_formatters = {
        "block": format_block_link,
        "image_path": format_image_url,
        "image_path_answered": format_image_url,
        "text_answered": format_truncated_text,
        "hint_path": format_image_url,
        "answers": format_answer_text
    }
    column_formatters_detail = {
        "block": format_block_link,
        "image_path": format_image_url,
        "image_path_answered": format_image_url,
        "hint_path": format_image_url,
        "text_answered": format_truncated_text,
        "answers": format_answer_text
    }

    def sort_query(self, stmt: Select, request: Request) -> Select:
        sort_by = request.query_params.get("sortBy")
        sort_order = request.query_params.get("sort")
        if sort_by == "block":
            if sort_order == "desc":
                stmt = stmt.join(Block).order_by(Block.title.desc())
            else:
                stmt = stmt.join(Block).order_by(Block.title.asc())
        return super().sort_query(stmt, request)

    @staticmethod
    def generate_unique_filename(original_filename: str) -> str:
        """Генерирует уникальное имя файла"""
        ext = original_filename.split('.')[-1]  # Получаем расширение файла
        unique_id = uuid.uuid4().hex  # Генерируем уникальный идентификатор
        return f"{unique_id}.{ext}"

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        if 'image_path' in data:
            file = data['image_path']
            if hasattr(file, 'filename') and hasattr(file, 'read') and file.filename:
                # Убедимся, что директория существует
                img_dir = Path("app/static/img")
                img_dir.mkdir(parents=True, exist_ok=True)
                
                # Удаляем старый файл, если он существует
                if model.image_path:
                    old_file_path = img_dir / model.image_path
                    if old_file_path.exists():
                        os.remove(old_file_path)
                
                # Генерируем уникальное имя файла
                unique_filename = self.generate_unique_filename(file.filename)
                
                file_content = await file.read()
                file_path = img_dir / unique_filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                # Сохраняем только имя файла в базу данных
                data['image_path'] = unique_filename
            else:
                # Если файл не загружен, устанавливаем None вместо объекта UploadFile
                if not is_created and model.image_path:  # Для редактирования - сохраняем текущее значение
                    data['image_path'] = model.image_path
                else:
                    data['image_path'] = None  # Для создания - устанавливаем None

        if 'image_path_answered' in data:
            file = data['image_path_answered']
            if hasattr(file, 'filename') and hasattr(file, 'read') and file.filename:
                # Убедимся, что директория существует
                img_dir = Path("app/static/img")
                img_dir.mkdir(parents=True, exist_ok=True)
                
                # Удаляем старый файл, если он существует
                if model.image_path_answered:
                    old_file_path = img_dir / model.image_path_answered
                    if old_file_path.exists():
                        os.remove(old_file_path)
                
                # Генерируем уникальное имя файла
                unique_filename = self.generate_unique_filename(file.filename)
                
                file_content = await file.read()
                file_path = img_dir / unique_filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                # Сохраняем только имя файла в базу данных
                data['image_path_answered'] = unique_filename
            else:
                # Если файл не загружен, устанавливаем None вместо объекта UploadFile
                if not is_created and model.image_path_answered:  # Для редактирования - сохраняем текущее значение
                    data['image_path_answered'] = model.image_path_answered
                else:
                    data['image_path_answered'] = None  # Для создания - устанавливаем None

        if 'hint_path' in data:
            file = data['hint_path']
            if hasattr(file, 'filename') and hasattr(file, 'read') and file.filename:
                # Убедимся, что директория существует
                img_dir = Path("app/static/img")
                img_dir.mkdir(parents=True, exist_ok=True)
                
                # Удаляем старый файл, если он существует
                if model.hint_path:
                    old_file_path = img_dir / model.hint_path
                    if old_file_path.exists():
                        os.remove(old_file_path)
                
                # Генерируем уникальное имя файла
                unique_filename = self.generate_unique_filename(file.filename)
                
                file_content = await file.read()
                file_path = img_dir / unique_filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                # Сохраняем только имя файла в базу данных
                data['hint_path'] = unique_filename
            else:
                # Если файл не загружен, устанавливаем None вместо объекта UploadFile
                if not is_created and model.hint_path:  # Для редактирования - сохраняем текущее значение
                    data['hint_path'] = model.hint_path
                else:
                    data['hint_path'] = None  # Для создания - устанавливаем None

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

        # Удаляем файл hint_path, если он существует
        if model.hint_path:
            file_path = Path("app/static/img") / model.hint_path
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
        Answer.id,
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

    column_sortable_list = [
        Answer.question,
    ]

    def sort_query(self, stmt: Select, request: Request) -> Select:
        sort_by = request.query_params.get("sortBy")
        sort_order = request.query_params.get("sort")
        if sort_by == "question":
            if sort_order == "desc":
                stmt = stmt.join(Question).order_by(Question.title.desc())
            else:
                stmt = stmt.join(Question).order_by(Question.title.asc())
        return super().sort_query(stmt, request)

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

class QuestionInsiderAdmin(ModelView, model=QuestionInsider):
    column_list = [
        QuestionInsider.id,
        QuestionInsider.question,
        QuestionInsider.user
    ]
    form_columns = [
        QuestionInsider.question,
        QuestionInsider.user
    ]
    form_ajax_refs = {
        'user': {
            'fields': ['full_name', 'telegram_username'],
            'order_by': 'full_name',
        }
    }

class SessionAdmin(ModelView, model=Session):
    column_list = [
        Session.id,
        Session.user_id,
        Session.token,
        Session.created_at,
        Session.expires_at,
        Session.is_active
    ]
    form_columns = [
        Session.user_id,
        Session.created_at,
        Session.expires_at,
        Session.is_active
    ]

class CommandsUserAdmin(ModelView, model=CommandsUser):
    column_list = [
        CommandsUser.command,
        CommandsUser.user,
        CommandsUser.role
    ]
    form_columns = [
        CommandsUser.command,
        CommandsUser.user,
        CommandsUser.role
    ]
    
    