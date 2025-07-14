"""
Настройки и конфигурация Prometheus метрик для FastAPI приложения.
"""
import time
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


# Кастомные метрики основного приложения
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status", "event_name"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "event_name"]
)

ACTIVE_REQUESTS = Gauge(
    "http_requests_active",
    "Number of active HTTP requests",
    ["event_name"]
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total number of HTTP errors",
    ["method", "endpoint", "error_type", "event_name"]
)

# Метрики для админки
ADMIN_REQUEST_COUNT = Counter(
    "admin_requests_total",
    "Total number of admin requests",
    ["method", "endpoint", "status", "admin_section"]
)

ADMIN_REQUEST_DURATION = Histogram(
    "admin_request_duration_seconds",
    "Admin request duration in seconds",
    ["method", "endpoint", "admin_section"]
)

ADMIN_ACTIVE_REQUESTS = Gauge(
    "admin_requests_active",
    "Number of active admin requests",
    ["admin_section"]
)

ADMIN_ERROR_COUNT = Counter(
    "admin_errors_total",
    "Total number of admin errors",
    ["method", "endpoint", "error_type", "admin_section"]
)

ADMIN_SESSION_DURATION = Histogram(
    "admin_session_duration_seconds",
    "Admin session duration in seconds",
    ["admin_section"]
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware для сбора кастомных метрик Prometheus."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        ACTIVE_REQUESTS.labels(event_name="unknown").inc()  # Считаем активные до определения event_name
        try:
            response = await call_next(request)
            event_name = getattr(request.state, 'event_name', 'unknown')
            # Записываем метрики успешного запроса
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                event_name=event_name
            ).inc()
            # Записываем длительность запроса
            duration = time.time() - start_time
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
                event_name=event_name
            ).observe(duration)
            return response
        except Exception as e:
            event_name = getattr(request.state, 'event_name', 'unknown')
            # Записываем метрики ошибки
            ERROR_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                error_type=type(e).__name__,
                event_name=event_name
            ).inc()
            # Записываем метрики неуспешного запроса
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500,
                event_name=event_name
            ).inc()
            # Записываем длительность запроса с ошибкой
            duration = time.time() - start_time
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
                event_name=event_name
            ).observe(duration)
            raise
        finally:
            event_name = getattr(request.state, 'event_name', 'unknown')
            ACTIVE_REQUESTS.labels(event_name=event_name).dec()


class AdminMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware для сбора метрик админки."""

    async def dispatch(self, request: Request, call_next):
        # Проверяем, является ли запрос админским
        if not request.url.path.startswith("/admin"):
            return await call_next(request)
        
        start_time = time.time()
        
        # Определяем секцию админки
        admin_section = self._get_admin_section(request.url.path)
        
        # Увеличиваем счетчик активных запросов админки
        ADMIN_ACTIVE_REQUESTS.labels(admin_section=admin_section).inc()
        
        try:
            response = await call_next(request)
            
            # Записываем метрики успешного запроса админки
            ADMIN_REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                admin_section=admin_section
            ).inc()
            
            # Записываем длительность запроса админки
            duration = time.time() - start_time
            ADMIN_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
                admin_section=admin_section
            ).observe(duration)
            
            return response
            
        except Exception as e:
            # Записываем метрики ошибки админки
            ADMIN_ERROR_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                error_type=type(e).__name__,
                admin_section=admin_section
            ).inc()
            
            # Записываем метрики неуспешного запроса админки
            ADMIN_REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500,
                admin_section=admin_section
            ).inc()
            
            # Записываем длительность запроса админки с ошибкой
            duration = time.time() - start_time
            ADMIN_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
                admin_section=admin_section
            ).observe(duration)
            
            raise
        finally:
            # Уменьшаем счетчик активных запросов админки
            ADMIN_ACTIVE_REQUESTS.labels(admin_section=admin_section).dec()
    
    def _get_admin_section(self, path: str) -> str:
        """Определяет секцию админки по пути."""
        if "/admin/login" in path:
            return "auth"
        elif "/admin/database" in path:
            return "database"
        elif "/admin/users" in path:
            return "users"
        elif "/admin/settings" in path:
            return "settings"
        elif "/admin/logs" in path:
            return "logs"
        else:
            return "other"


def setup_prometheus_metrics(app: FastAPI) -> None:
    """Настройка детальных метрик Prometheus."""
    
    # Создаем инструментатор с кастомными настройками
    instrumentator = Instrumentator(
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/static"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="fastapi_requests_inprogress",
        inprogress_labels=True,
    )
    
    # Добавляем стандартные метрики
    instrumentator.add(metrics.request_size(should_include_handler=True, should_include_method=True, should_include_status=True))
    instrumentator.add(metrics.response_size(should_include_handler=True, should_include_method=True, should_include_status=True))
    instrumentator.add(metrics.latency(should_include_handler=True, should_include_method=True, should_include_status=True))
    instrumentator.add(metrics.requests(should_include_handler=True, should_include_method=True, should_include_status=True))
    
    # Удаляем metrics.response_time, так как его нет в библиотеке
    # instrumentator.add(metrics.response_time(should_include_handler=True, should_include_method=True, should_include_status=True))
    
    # Инструментируем приложение
    instrumentator.instrument(app)
    
    # Экспонируем метрики на эндпоинте /metrics
    instrumentator.expose(app, include_in_schema=False, should_gzip=True)
    
    logger.info("Prometheus metrics configured successfully") 