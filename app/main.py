from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator, List, Dict, Any
from fastapi import FastAPI, APIRouter, Request, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
import time
import urllib.parse

from app.quest.router import router as router_quest
from app.auth.router import router as router_auth
from app.cms.router import init_admin
from app.utils.template import render_template
from app.config import event_config, DEBUG, BASE_URL

# Настройки безопасности
# Получаем домен из BASE_URL для добавления в разрешенные хосты и источники
parsed_url = urllib.parse.urlparse(BASE_URL)
base_domain = parsed_url.netloc
base_scheme = parsed_url.scheme

# Добавляем gopass.dev и hserun.gopass.dev в разрешенные хосты
ALLOWED_HOSTS = [
    "localhost", "127.0.0.1", "localhost:8000",
    base_domain
]

ALLOWED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8000",
    BASE_URL,  # Добавляем полный URL из конфига
    f"{base_scheme}://{base_domain}"  # Добавляем URL с извлеченным доменом
]
# Максимальный размер тела запроса (10 МБ)
MAX_BODY_SIZE = 3 * 1024 * 1024  
# Ограничение количества запросов (100 запросов в минуту)
RATE_LIMIT = 300
RATE_PERIOD = 60  # секунд

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения количества запросов с одного IP."""
    
    def __init__(self, app, rate_limit=RATE_LIMIT, period=RATE_PERIOD):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.period = period
        self.ips = {}
        
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()
        
        # Очистка устаревших записей
        if client_ip in self.ips:
            self.ips[client_ip] = [timestamp for timestamp in self.ips[client_ip] 
                                if current_time - timestamp < self.period]
        else:
            self.ips[client_ip] = []
            
        # Проверка на превышение лимита
        if len(self.ips[client_ip]) >= self.rate_limit:
            return Response(
                content="Too many requests", 
                status_code=429,
                headers={"Retry-After": str(self.period)}
            )
            
        # Добавляем текущий запрос
        self.ips[client_ip].append(current_time)
        
        # Пропускаем запрос дальше
        response = await call_next(request)
        return response

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения размера тела запроса."""
    
    def __init__(self, app, max_size: int = MAX_BODY_SIZE):
        super().__init__(app)
        self.max_size = max_size
        
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return Response(
                content="Request body too large", 
                status_code=413
            )
            
        response = await call_next(request)
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления заголовков безопасности."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Защита от XSS
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Защита от кликджекинга
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Защита от MIME-типов
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Запрет кеширования для приватных данных
        if request.url.path.startswith(("/api/auth/me", "/api/quest")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
        
        # HSTS для перенаправления на HTTPS
        if not DEBUG:  # Только в production
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Устанавливаем политику реферера для приватных данных
        if request.url.path.startswith("/api/"):
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        else:
            response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        
        # Content-Security-Policy для защиты от XSS
        # Включаем возможность подключения к домену из BASE_URL
        base_domain_csp = f"{base_scheme}://{base_domain}"
        if not request.url.path.startswith("/admin"):  # Не добавляем для админки
            response.headers["Content-Security-Policy"] = (
                f"default-src 'self' {base_domain_csp}; "
                f"script-src 'self' 'unsafe-inline' {base_domain_csp}; "
                f"style-src 'self' 'unsafe-inline' {base_domain_csp}; "
                f"img-src 'self' data: {base_domain_csp}; "
                f"connect-src 'self' {base_domain_csp}; "
                "frame-ancestors 'self'; "
                "form-action 'self'"
            )
        
        return response

class SQLInjectionProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware для защиты от SQL-инъекций."""
    
    def __init__(self, app):
        super().__init__(app)
        # Паттерны для обнаружения возможных SQL-инъекций
        self.sql_patterns = [
            r"(\b(select|insert|update|delete|drop|alter|exec|union|where)\b)",
            r"(--|;|\/\*|\*\/|@@|char|nchar|varchar|nvarchar|cursor|declare)",
            r"(\bfrom\b.*\bwhere\b|\bunion\b.*\bselect\b)",
            r"(xp_cmdshell|xp_reg|sp_configure|sp_executesql)"
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Проверяем только запросы с телом
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Получаем тело запроса
                body = await request.json()
                
                # Проверяем на наличие паттернов SQL-инъекций
                if self._check_sql_injection(body):
                    logger.warning(f"Обнаружена попытка SQL-инъекции: {body}")
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Недопустимые данные запроса"}
                    )
            except Exception:
                # Если не удалось прочитать JSON, продолжаем обработку
                pass
        
        # Продолжаем обработку запроса
        response = await call_next(request)
        return response
    
    def _check_sql_injection(self, data):
        """Проверяет данные на наличие паттернов SQL-инъекций"""
        import re
        
        # Рекурсивно проверяем все строковые значения
        if isinstance(data, dict):
            return any(self._check_sql_injection(v) for v in data.values())
        elif isinstance(data, list):
            return any(self._check_sql_injection(item) for item in data)
        elif isinstance(data, str):
            # Проверяем каждый паттерн
            data_lower = data.lower()
            for pattern in self.sql_patterns:
                if re.search(pattern, data_lower):
                    return True
        
        return False

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

    # Настройка глобальных обработчиков исключений
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Обработчик HTTP исключений."""
        logger.error(f"HTTP ошибка {exc.status_code}: {exc.detail}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail,
                    "type": "http_error"
                }
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Обработчик ошибок валидации запросов."""
        errors = []
        for error in exc.errors():
            error_info = {
                "field": ".".join(str(loc) for loc in error["loc"]) if "loc" in error else "",
                "message": error["msg"],
                "type": error["type"]
            }
            errors.append(error_info)
            
        logger.error(f"Ошибка валидации: {errors}")
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "ok": False,
                "error": {
                    "code": 422,
                    "message": "Ошибка валидации данных",
                    "type": "validation_error",
                    "details": errors
                }
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Обработчик общих исключений."""
        error_id = f"{time.time():.0f}"  # Генерируем ID ошибки для отслеживания
        
        error_info = {
            "path": request.url.path,
            "method": request.method,
            "error_id": error_id,
            "error": str(exc),
            "traceback": traceback.format_exc()
        }
        
        logger.error(f"Неожиданная ошибка [{error_id}]: {str(exc)}\n{traceback.format_exc()}")
        
        response = {
            "ok": False,
            "error": {
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Внутренняя ошибка сервера",
                "type": "server_error",
                "error_id": error_id
            }
        }
        
        # В режиме отладки добавляем информацию об ошибке
        if DEBUG:
            response["error"]["debug_info"] = {
                "exception": str(exc),
                "traceback": traceback.format_exc()
            }
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response
        )

    # Настройка CORS с более строгими ограничениями
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        max_age=3600,  # 1 час
    )
    
    # Добавляем middleware для проверки хостов
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    
    # Добавляем middleware для безопасности
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Ограничиваем размер тела запроса
    app.add_middleware(MaxBodySizeMiddleware)
    
    # Добавляем rate limiting только в production
    if not DEBUG:
        app.add_middleware(RateLimitMiddleware)

    # Добавляем защиту от SQL-инъекций
    app.add_middleware(SQLInjectionProtectionMiddleware)

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

        @root_router.get("/qr/verify", tags=["qr_verify"])
        async def qr_verify_page(request: Request):
            return render_template(request, "qrverify.html")
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
