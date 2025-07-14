import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Добавляем путь к приложению
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))
sys.path.append('/projects/hse_run_full/backend')

# Импортируем базовые модели
from app.auth.models import (
    User, Role, Command, CommandsUser, UserProfile, 
    Event, RoleUserCommand, CommandInvite
)

# Создаем отдельную модель Language для бота без связей
from sqlalchemy.orm import Mapped, mapped_column
from app.dao.database import Base, str_uniq

class BotLanguage(Base):
    """Модель Language для бота без связей с блоками"""
    __tablename__ = 'languages'
    __table_args__ = {'extend_existing': True}
    
    name: Mapped[str_uniq]
    
    def __repr__(self):
        return f"{self.name}"

from app.logger import logger
from dotenv import load_dotenv

load_dotenv()

# Конфигурация админки бота
BOT_ADMIN_USERNAME = os.getenv("BOT_ADMIN_USERNAME", "bot_admin")
BOT_ADMIN_PASSWORD = os.getenv("BOT_ADMIN_PASSWORD", "bot_admin123")
SECRET_KEY = os.getenv("BOT_ADMIN_SECRET_KEY", "bot-registration-admin-secret-key")

# Подключение к БД бота (может быть отдельная или основная)
BOT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./registration_bot.db")
bot_engine = create_async_engine(BOT_DATABASE_URL, echo=False)
bot_session_maker = async_sessionmaker(bot_engine, expire_on_commit=False)


class BotAdminAuth(AuthenticationBackend):
    """Аутентификация для админ-панели бота"""
    
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]
        
        if username == BOT_ADMIN_USERNAME and password == BOT_ADMIN_PASSWORD:
            request.session.update({"bot_admin_token": "authenticated"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("bot_admin_token")
        return token == "authenticated"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Жизненный цикл приложения"""
    logger.info("🤖 Запуск админ-панели бота регистрации...")
    
    # Инициализация при запуске
    try:
        # Проверяем подключение к БД
        from sqlalchemy import text
        async with bot_session_maker() as session:
            await session.execute(text("SELECT 1"))
        logger.info("✅ Подключение к базе данных бота установлено")
        logger.info(f"📊 БД: {BOT_DATABASE_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД бота: {e}")
        raise
    
    yield
    
    logger.info("🛑 Завершение работы админ-панели бота...")


def create_bot_admin_app() -> FastAPI:
    """Создание FastAPI приложения для админки бота"""
    
    app = FastAPI(
        title="HSE Quest Registration Bot Admin",
        description="Административная панель для управления ботом регистрации",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Middleware
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Создаем админку
    admin = Admin(
        app=app, 
        engine=bot_engine, 
        authentication_backend=BotAdminAuth(secret_key=SECRET_KEY),
        title="Bot Registration Admin",
        logo_url=None
    )
    
    # Админ-панели для моделей бота
    setup_bot_admin_views(admin)
    
    return app


def setup_bot_admin_views(admin: Admin):
    """Настройка админ-панелей для моделей бота регистрации"""
    
    # Пользователи (с фокусом на регистрацию)
    class BotUserAdmin(ModelView, model=User):
        column_list = [
            User.id, User.full_name, User.telegram_id, 
            User.telegram_username, User.role, User.is_looking_for_friends,
            User.created_at
        ]
        column_searchable_list = [User.full_name, User.telegram_username]
        column_sortable_list = [User.id, User.full_name, User.created_at]
        # Убираем все фильтры - SQLAdmin не может их корректно обработать
        column_filters = []
        
        # Поля для создания/редактирования
        form_columns = [
            User.full_name, User.telegram_id, User.telegram_username, 
            User.role, User.is_looking_for_friends
        ]
        
        # Настройки отображения
        name = "👥 Пользователи"
        name_plural = "👥 Пользователи" 
        icon = "fa-solid fa-users"
        page_size = 50
        
        # Дополнительные настройки для удобства
        column_default_sort = [(User.created_at, True)]  # Сортировка по дате создания (новые сверху)
    
    # Профили пользователей (email и доп. информация)
    class BotUserProfileAdmin(ModelView, model=UserProfile):
        column_list = [UserProfile.id, "user", UserProfile.email, UserProfile.created_at]
        column_searchable_list = [UserProfile.email]
        column_sortable_list = [UserProfile.id, UserProfile.created_at]
        
        form_columns = ["user", UserProfile.email]
        
        name = "📧 Профили пользователей"
        name_plural = "📧 Профили пользователей"
        icon = "fa-solid fa-address-card"
        page_size = 50
        
        column_default_sort = [(UserProfile.created_at, True)]
    
    # Команды (основной фокус бота)
    class BotCommandAdmin(ModelView, model=Command):
        column_list = [
            Command.id, Command.name, Command.event, Command.language_id, 
            Command.created_at
        ]
        column_searchable_list = [Command.name]
        column_sortable_list = [Command.id, Command.name, Command.created_at]
        # Убираем проблемные фильтры для relationship полей
        column_filters = []
        
        form_columns = [Command.name, Command.event, Command.language_id]
        
        name = "⚔️ Команды"
        name_plural = "⚔️ Команды"
        icon = "fa-solid fa-users-gear"
        page_size = 50
        
        column_default_sort = [(Command.created_at, True)]
    
    # Участники команд (управление составом)
    class BotCommandsUserAdmin(ModelView, model=CommandsUser):
        column_list = ["command", "user", CommandsUser.role]
        # Убираем проблемные фильтры для relationship полей
        column_filters = []
        column_sortable_list = []
        
        form_columns = ["command", "user", CommandsUser.role]
        
        name = "👥 Участники команд"
        name_plural = "👥 Участники команд"
        icon = "fa-solid fa-user-group"
        page_size = 100
    
    # Приглашения команд (UUID ссылки)
    class BotCommandInviteAdmin(ModelView, model=CommandInvite):
        column_list = [
            CommandInvite.id, "command", 
            CommandInvite.invite_uuid, CommandInvite.created_at
        ]
        column_searchable_list = [CommandInvite.invite_uuid]
        column_sortable_list = [CommandInvite.id, CommandInvite.created_at]
        # Убираем проблемные фильтры для relationship полей
        column_filters = []
        
        form_columns = ["command", CommandInvite.invite_uuid]
        
        name = "🔗 Приглашения команд"
        name_plural = "🔗 Приглашения команд"
        icon = "fa-solid fa-link"
        page_size = 50
        
        column_default_sort = [(CommandInvite.created_at, True)]
    
    # Роли системы
    class BotRoleAdmin(ModelView, model=Role):
        column_list = [Role.id, Role.name, Role.created_at]
        column_searchable_list = [Role.name]
        column_sortable_list = [Role.id, Role.name, Role.created_at]
        
        form_columns = [Role.name]
        
        name = "🎭 Роли системы"
        name_plural = "🎭 Роли системы"
        icon = "fa-solid fa-user-tag"
    
    # Роли в командах
    class BotRoleUserCommandAdmin(ModelView, model=RoleUserCommand):
        column_list = [RoleUserCommand.id, RoleUserCommand.name, RoleUserCommand.created_at]
        column_searchable_list = [RoleUserCommand.name]
        column_sortable_list = [RoleUserCommand.id, RoleUserCommand.name, RoleUserCommand.created_at]
        
        form_columns = [RoleUserCommand.name]
        
        name = "👑 Роли в командах"
        name_plural = "👑 Роли в командах"
        icon = "fa-solid fa-crown"
    
    # Мероприятия
    class BotEventAdmin(ModelView, model=Event):
        column_list = [Event.id, Event.name, Event.start_time, Event.end_time, Event.created_at]
        column_searchable_list = [Event.name]
        column_sortable_list = [Event.id, Event.name, Event.start_time, Event.created_at]
        
        form_columns = [Event.name, Event.start_time, Event.end_time]
        
        name = "📅 Мероприятия"
        name_plural = "📅 Мероприятия"
        icon = "fa-solid fa-calendar-days"
    
    # Языки программирования
    class BotLanguageAdmin(ModelView, model=BotLanguage):
        column_list = [BotLanguage.id, BotLanguage.name, BotLanguage.created_at]
        column_searchable_list = [BotLanguage.name]
        column_sortable_list = [BotLanguage.id, BotLanguage.name, BotLanguage.created_at]
        
        form_columns = [BotLanguage.name]
        
        name = "💻 Языки программирования"
        name_plural = "💻 Языки программирования"
        icon = "fa-solid fa-code"
    
    # Регистрируем админ-панели в порядке важности для бота
    admin.add_view(BotUserAdmin)
    admin.add_view(BotUserProfileAdmin)
    admin.add_view(BotCommandAdmin)
    admin.add_view(BotCommandsUserAdmin)
    admin.add_view(BotCommandInviteAdmin)
    admin.add_view(BotRoleAdmin)
    admin.add_view(BotRoleUserCommandAdmin)
    admin.add_view(BotEventAdmin)
    admin.add_view(BotLanguageAdmin)


# Создание приложения
app = create_bot_admin_app()


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🤖 Запуск админ-панели бота регистрации...")
    logger.info(f"👤 Логин: {BOT_ADMIN_USERNAME}")
    logger.info(f"🔑 Пароль: {'*' * len(BOT_ADMIN_PASSWORD)}")
    logger.info("🌐 Админ-панель бота будет доступна по адресу: http://localhost:8002/admin")
    logger.info(f"📊 База данных: {BOT_DATABASE_URL}")
    
    uvicorn.run(
        "bot_admin_app:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    ) 