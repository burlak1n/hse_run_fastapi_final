from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.quest.router import router as router_quest
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
        title="HSE RUN",
        description=(
            "HSE RUN - культурно-исторический квест по Москве"
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

        @root_router.get("/quest/{block_id}", tags=["quest"])
        async def quest_block_page(request: Request, block_id: int):
            return render_template(request, "block.html", {"block_id": block_id})

        @root_router.get("/profile", tags=["profile"])
        async def profile_page(request: Request):
            return render_template(request, "profile.html")
    else:
        pass
        # @root_router.get("/", tags=["root"])
        # async def home_page(request: Request):
        #     return {"ok": True}
        # Serve Vue app
        # Mount Vue frontend
        # frontend_path = os.path.join(os.path.dirname(__file__), "../frontend/public")
        # app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")
        # app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "../src/assets")), name="assets")
        # @root_router.get("/{full_path:path}")
        # async def serve_vue_app(full_path: str):
        #     return FileResponse(os.path.join(frontend_path, "index.html"))
    # Создаем основной API роутер

    @root_router.get("/qr/verify", tags=["qr_verify"])
    async def qr_verify_page(request: Request):
        return render_template(request, "qrverify.html")

    app.include_router(root_router)

    api_router = APIRouter(prefix='/api')

    # Подключаем все роутеры к API роутеру
    api_router.include_router(router_auth, prefix='/auth', tags=['Auth'])
    api_router.include_router(router_quest, prefix='/quest', tags=['Quest'])

    # Подключаем основной API роутер к приложению
    app.include_router(api_router)
    
    # Указываем протокол для админки
    base_url = '/admin/database'
    init_admin(app, base_url=base_url)

# Создание экземпляра приложения
app = create_app()
