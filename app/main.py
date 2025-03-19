from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.auth.router import router as router_auth
from app.cms.router import init_admin
from app.utils.template import render_template
from app.config import event_config, DEBUG

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[dict, None]:
    """Управление жизненным циклом приложения."""
    logger.info("Инициализация приложения...")
    yield
    logger.info("Завершение работы приложения...")


def create_app() -> FastAPI:
    """
   Создание и конфигурация FastAPI приложения.

   Returns:
       Сконфигурированное приложение FastAPI
   """
    app = FastAPI(
        title="Стартовая сборка FastAPI",
        description=(
            "Стартовая сборка с интегрированной SQLAlchemy 2 для разработки FastAPI приложений с продвинутой "
            "архитектурой, включающей авторизацию, аутентификацию и управление ролями пользователей.\n\n"
            "**Автор проекта**: Яковенко Алексей\n"
            "**Telegram**: https://t.me/PythonPathMaster"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # Настройка CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Монтирование статических файлов
    app.mount(
        '/static',
        StaticFiles(directory='app/static'),
        name='static'
    )

    # Регистрация роутеров
    register_routers(app)

    return app


def register_routers(app: FastAPI) -> None:
    """Регистрация роутеров приложения."""
    # Корневой роутер
    root_router = APIRouter()

    if DEBUG:
        @root_router.get("/", tags=["root"])
        async def home_page(request: Request):
            return render_template(request, "index.html", {"event_config": event_config})

        @root_router.get("/registration", tags=["registration"])
        async def registration_page(request: Request):
            return render_template(request, "registration.html", {"event_config": event_config})

        @root_router.get("/quest", tags=["quest"])
        async def quest_page(request: Request):
            return render_template(request, "quest.html")

        @root_router.get("/profile", tags=["profile"])
        async def profile_page(request: Request):
            return render_template(request, "profile.html")
    else:
        @root_router.get("/", tags=["root"])
        async def home_page(request: Request):
            return {"ok": True}
    # Подключение роутеров
    app.include_router(root_router, tags=["root"])
    app.include_router(router_auth, prefix='/api/auth', tags=['Auth'])
    init_admin(app, base_url='/cms')

# Создание экземпляра приложения
app = create_app()
