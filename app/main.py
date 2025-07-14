import time
import traceback
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
# FastAPI Cache imports removed
from loguru import logger
# Импорты CSRF
# from fastapi_csrf_protect import CsrfProtect # Removed CSRF import
# from fastapi_csrf_protect.exceptions import CsrfProtectError # Removed CSRF import
from pydantic import BaseModel
from redis import asyncio as aioredis
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.redis_session import init_redis_session_service
from app.auth.router import router as router_auth
from app.cms.router import init_admin
from app.config import (BASE_URL, DEBUG, event_config,
                        get_event_name_by_domain, settings)
# Import logger and context var from app.logger
from app.logger import request_id_context
from app.quest.router import router as router_quest
# Import FastStream broker
from app.tasks.cleanup import broker as cleanup_broker
from app.utils.template import render_template
# Import Prometheus metrics
from app.prometheus_metrics import (
    PrometheusMetricsMiddleware,
    AdminMetricsMiddleware,
    setup_prometheus_metrics
)

# Настройки безопасности
# Получаем домен из BASE_URL для добавления в разрешенные хосты и источники
parsed_url = urllib.parse.urlparse(BASE_URL)
base_domain = parsed_url.netloc
base_scheme = parsed_url.scheme

# Добавляем gopass.dev и hserun.gopass.dev в разрешенные хосты
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "localhost:8000", base_domain, "technoquestcroc.ru", "172.19.0.1"]

ALLOWED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8000",
    BASE_URL,  # Добавляем полный URL из конфига
    f"{base_scheme}://{base_domain}",  # Добавляем URL с извлеченным доменом
    "https://technoquestcroc.ru",  # Добавляем домен для KRUN события
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
            self.ips[client_ip] = [
                timestamp
                for timestamp in self.ips[client_ip]
                if current_time - timestamp < self.period
            ]
        else:
            self.ips[client_ip] = []

        # Проверка на превышение лимита
        if len(self.ips[client_ip]) >= self.rate_limit:
            return Response(
                content="Too many requests",
                status_code=429,
                headers={"Retry-After": str(self.period)},
            )

        # Добавляем текущий запрос
        self.ips[client_ip].append(current_time)

        # Пропускаем запрос дальше
        response = await call_next(request)
        return response


# Middleware for adding Request ID
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        token = request_id_context.set(request_id)
        request.state.request_id = request_id
        logger.bind(request_id=request_id).info(
            f"Request started: {request.method} {request.url.path}"
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.bind(request_id=request_id).info(
                f"Request finished: {response.status_code}"
            )
        except Exception as e:
            logger.bind(request_id=request_id).exception(
                "Unhandled exception during request"
            )
            raise e
        finally:
            request_id_context.reset(token)
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения размера тела запроса."""

    def __init__(self, app, max_size: int = MAX_BODY_SIZE):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return Response(content="Request body too large", status_code=413)

        response = await call_next(request)
        return response


class EventDomainMiddleware(BaseHTTPMiddleware):
    """Middleware для определения события по домену."""

    async def dispatch(self, request: Request, call_next):
        # Получаем домен из заголовка Host (приоритет) или X-Forwarded-Host
        host = request.headers.get("host", "")
        if not host:
            # Fallback на X-Forwarded-Host если Host не установлен
            host = request.headers.get("x-forwarded-host", "")
        
        if host:
            # Убираем порт если есть (гарантированно)
            domain = host.split(":")[0]
            event_name = get_event_name_by_domain(domain)
            request.state.event_name = event_name
            logger.info(f"Определено событие '{event_name}' для домена '{domain}' (host header: {host})")
        else:
            # Fallback на дефолтное событие
            request.state.event_name = "HSERUN29"
            logger.warning(
                "Не удалось определить домен, используется дефолтное событие"
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
        # HTTP caching removed

        # HSTS для перенаправления на HTTPS
        if not DEBUG:  # Только в production
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Устанавливаем политику реферера для приватных данных
        if request.url.path.startswith("/api/"):
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        else:
            response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"

        # Content-Security-Policy для защиты от XSS
        # Используем только текущий домен для CSP
        current_host = request.headers.get("host", "")
        if current_host:
            # Убираем порт если есть
            current_domain = current_host.split(":")[0]
            current_domain_csp = f"https://{current_domain}"
        else:
            # Fallback на домен из BASE_URL
            current_domain_csp = f"{base_scheme}://{base_domain}"
        
        if not request.url.path.startswith("/cms"):  # Не добавляем для админки
            response.headers["Content-Security-Policy"] = (
                f"default-src 'self' {current_domain_csp}; "
                f"script-src 'self' 'unsafe-inline' {current_domain_csp}; "
                f"style-src 'self' 'unsafe-inline' {current_domain_csp}; "
                f"img-src 'self' data: {current_domain_csp}; "
                f"connect-src 'self' {current_domain_csp}; "
                "frame-ancestors 'self'; "
                "form-action 'self'"
            )

        return response





# Настройка Middleware (CORS, TrustedHost, Security, Rate Limiting)
def setup_middleware(app: FastAPI):
    # Add Request ID Middleware (should be one of the first)
    app.add_middleware(RequestIdMiddleware)

    # Добавляем middleware для определения события по домену
    app.add_middleware(EventDomainMiddleware)

    # Добавляем middleware для сбора метрик Prometheus
    app.add_middleware(PrometheusMetricsMiddleware)

    # Добавляем middleware для сбора метрик админки
    app.add_middleware(AdminMetricsMiddleware)

    # Настройка CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "OPTIONS",
            "PUT",
            "DELETE",
            "PATCH",
        ],  # Добавляем методы
        allow_headers=["*"],  # Разрешаем все заголовки, включая X-CSRF-Token
        max_age=3600,
    )

    # Проверка хостов
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    # Добавляем middleware для проверки размера тела запроса
    app.add_middleware(MaxBodySizeMiddleware)

    # Отключено, так как может вызывать проблемы с legitimate запросами
    # app.add_middleware(SQLInjectionProtectionMiddleware)

    # Добавляем middleware для заголовков безопасности
    app.add_middleware(SecurityHeadersMiddleware)

    # Ограничение частоты запросов (только в production)
    if not DEBUG:
        # app.add_middleware(RateLimitMiddleware)
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управление жизненным циклом приложения."""
    logger.info("Инициализация приложения...")
    if settings.USE_REDIS:
        logger.info("Redis is ENABLED. Initializing Redis features...")
        try:
            # Start FastStream broker first
            await cleanup_broker.start()
            logger.info("FastStream broker started.")

            # Initialize Redis session service using FastStream broker
            await init_redis_session_service(cleanup_broker)
            logger.info("Redis session service initialized.")

        except Exception:
            logger.exception(
                "Failed to initialize Redis features. Check Redis connection and settings."
            )
            # Decide if startup should fail. For now, continue without Redis.
            settings.USE_REDIS = False  # Disable Redis usage if init fails
            logger.warning("Redis initialization failed.")
    else:
        logger.info("Redis is DISABLED.")

    yield  # Application runs here

    logger.info("Завершение работы приложения...")
    if settings.USE_REDIS:
        # Stop FastStream broker if it was used
        try:
            await cleanup_broker.stop()
            logger.info("FastStream broker stopped.")
        except Exception:
            logger.exception("Error stopping FastStream broker.")

    # Cache cleanup removed


# Unified Error Handlers


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handles FastAPI validation errors, returning a unified error response."""
    errors = []
    for error in exc.errors():
        errors.append(
            ErrorDetail(
                field=".".join(str(loc) for loc in error["loc"])
                if "loc" in error
                else None,
                message=error["msg"],
                type=error["type"],
            )
        )
    logger.warning(
        f"Validation error for {request.method} {request.url.path}: {errors}"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(error=errors).dict(),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handles FastAPI/Starlette HTTP exceptions, returning a unified error response."""
    error_detail = ErrorDetail(message=exc.detail, type="http_exception")
    logger.warning(
        f"HTTP exception for {request.method} {request.url.path}: {exc.status_code} - {exc.detail}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=error_detail).dict(),
        headers=getattr(exc, "headers", None),  # Preserve original headers if any
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handles all other exceptions, returning a generic unified error response."""
    # Log the full traceback for unexpected errors
    tb_str = "".join(traceback.format_exception(exc))
    logger.error(
        f"Unhandled exception for {request.method} {request.url.path}:\n{tb_str}"
    )

    error_detail = ErrorDetail(
        message="Internal Server Error"
        if not DEBUG
        else str(exc),  # Avoid leaking details in production
        type=exc.__class__.__name__,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(error=error_detail).dict(),
    )


# Unified Error Response Model
class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail | List[ErrorDetail]


def create_app() -> FastAPI:
    """
    Создает и настраивает экземпляр FastAPI приложения.
    Включает в себя настройку middleware, регистрацию роутеров,
    обработчики ошибок и статические файлы.
    """

    app = FastAPI(
        title=event_config.name,
        description=event_config.description,
        version=event_config.version,
        debug=DEBUG,
        lifespan=lifespan,
        # Add unified exception handlers
        exception_handlers={
            RequestValidationError: validation_exception_handler,
            StarletteHTTPException: http_exception_handler,
            Exception: general_exception_handler,
        },
    )

    # Настройка middleware
    setup_middleware(app)

    # Монтирование статических файлов
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

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
            return render_template("index.html", request, {"event_config": event_config})

        @root_router.get("/registration", tags=["registration"])
        async def registration_page(request: Request):
            return render_template("registration.html", request, {"event_config": event_config})

        @root_router.get("/quest", tags=["quest"])
        async def quest_page(request: Request):
            return render_template("quest.html", request)

        @root_router.get("/quest/{block_id}", tags=["quest"])
        async def quest_block_page(request: Request, block_id: int):
            return render_template("block.html", request, {"block_id": block_id})

        @root_router.get("/profile", tags=["profile"])
        async def profile_page(request: Request):
            return render_template("profile.html", request)

        @root_router.get("/qr/verify", tags=["qr_verify"])
        async def qr_verify_page(request: Request):
            return render_template("qrverify.html", request)
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

    api_router = APIRouter(prefix="/api")

    # Подключаем все роутеры к API роутеру
    api_router.include_router(router_auth, prefix="/auth", tags=["Auth"])
    api_router.include_router(router_quest, prefix="/quest", tags=["Quest"])

    # Подключаем основной API роутер к приложению
    app.include_router(api_router)

    # Указываем протокол для админки
    base_url = "/admin/database"
    init_admin(app, base_url=base_url)


# Создание экземпляра приложения
app = create_app()

# Настройка Prometheus метрик
setup_prometheus_metrics(app)
