from sqladmin import Admin, ModelView, BaseView
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse, FileResponse, JSONResponse, Response
from starlette.types import ASGIApp
from sqlalchemy.ext.asyncio import AsyncSession
from functools import wraps
from typing import Any, Dict, List, Optional, Callable, TypeVar, Union
import os
from PIL import Image, ImageDraw, ImageFont
import io
import uuid
import json
from sqlalchemy import func, select, text, cast, Date

from app.config import DEBUG
from app.dao.database import engine
from app.cms import views
from app.dependencies.auth_dep import get_access_token
from app.dependencies.template_dep import get_templates
from app.auth.dao import UsersDAO, SessionDAO
from app.auth.models import User
from app.logger import logger

# Определяем возвращаемый тип для декораторов
T = TypeVar('T')

# Получаем шаблонизатор
templates = get_templates()

class AdminView(ModelView):
    """Базовый класс для представлений админки с проверкой роли организатора."""
    
    async def is_accessible(self, request: Request) -> bool:
        """Проверяет доступ к представлению."""
        user = request.scope.get("user")
        return user is not None and hasattr(user, "role") and user.role.name == "organizer"


class AdminPage(BaseView):
    """Базовый класс для страниц админки."""
    
    async def is_visible(self, request: Request) -> bool:
        """Определяет видимость в меню."""
        user = request.scope.get("user")
        return user is not None and hasattr(user, "role") and user.role.name == "organizer"
    
    async def is_accessible(self, request: Request) -> bool:
        """Проверяет доступ к представлению."""
        user = request.scope.get("user")
        return user is not None and hasattr(user, "role") and user.role.name == "organizer"


class AdminDashboardView(AdminPage):
    """Панель управления для администраторов."""
    name = "Панель управления"
    icon = "fa-solid fa-gauge"

    async def dashboard(self, request: Request) -> HTMLResponse:
        """Отображает страницу панели управления."""
        user = request.scope.get("user")
        return templates.TemplateResponse(
            "admin/dashboard.html",
            {"request": request, "user": user}
        )

    def register(self, admin: Admin) -> None:
        """Регистрирует маршрут для панели управления."""
        admin.app.get("/admin/")(self.dashboard)
        admin.app.get("/admin")(self.dashboard)


class AdminRiddleView(AdminPage):
    """Представление для создания загадок."""
    name = "Создание загадок"
    icon = "fa-solid fa-puzzle-piece"
    
    # Константы для генерации изображений
    BACKGROUND_IMAGE = "app/static/img/riddle_bg.jpg"  # Путь к базовому изображению
    FONT_PATH = "app/static/fonts/Involve-Regular.ttf"
    
    async def get_riddle_page(self, request: Request) -> HTMLResponse:
        """Отображает страницу создания загадки."""
        return templates.TemplateResponse(
            "admin/riddle.html",
            {"request": request}
        )
    
    async def generate_riddle(self, 
                             request: Request, 
                             text: str = Form(...),
                             font_size: int = Form(36),
                             text_color: str = Form("#ffffff"),
                             text_align: str = Form("left"),
                             vertical_position: str = Form("middle")) -> Response:
        """Генерирует изображение с загадкой и возвращает его напрямую клиенту."""
        try:
            # Проверяем существование фонового изображения
            if not os.path.exists(self.BACKGROUND_IMAGE):
                # Если фон не найден, создаем простой черный фон
                bg_image = Image.new('RGB', (800, 600), color='black')
            else:
                # Загружаем фоновое изображение
                bg_image = Image.open(self.BACKGROUND_IMAGE)
            
            # Создаем объект для рисования на изображении
            draw = ImageDraw.Draw(bg_image)
            
            # Загружаем шрифт или используем стандартный, если не найден
            try:
                font = ImageFont.truetype(self.FONT_PATH, font_size)
            except IOError:
                # Используем стандартный шрифт, если указанный не найден
                font = ImageFont.load_default()
            
            # Преобразуем hex-цвет в RGB
            color = text_color.lstrip('#')
            rgb_color = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            
            # Определяем размеры контейнера для текста
            # Ограничиваем текст до 70% ширины и 60% высоты изображения
            container_width = int(bg_image.width * 0.7)
            container_height = int(bg_image.height * 0.6)
            
            # Определяем позицию контейнера на изображении
            container_left = (bg_image.width - container_width) // 2
            
            if vertical_position == "top":
                container_top = int(bg_image.height * 0.1)  # 10% сверху
            elif vertical_position == "bottom":
                container_top = int(bg_image.height * 0.9) - container_height  # 10% снизу
            else:  # middle
                container_top = (bg_image.height - container_height) // 2
            
            # Разбиваем текст на строки
            lines = text.strip().split('\n')
            
            # Определяем размеры текста для позиционирования
            line_heights = []
            line_widths = []
            
            # Получаем размеры каждой строки
            for line in lines:
                try:
                    # В более новых версиях Pillow
                    text_bbox = draw.textbbox((0, 0), line, font=font)
                    width = text_bbox[2] - text_bbox[0]
                    height = text_bbox[3] - text_bbox[1]
                except AttributeError:
                    # В старых версиях Pillow
                    width, height = draw.textsize(line, font=font)
                
                line_widths.append(width)
                line_heights.append(height)
            
            # Проверяем, если текст слишком широкий для контейнера
            is_too_wide = any(width > container_width for width in line_widths)
            if is_too_wide:
                # Уменьшаем размер шрифта, чтобы текст поместился
                scale_factor = min(container_width / max(line_widths), 1.0) * 0.95  # 5% запас
                new_font_size = int(font_size * scale_factor)
                try:
                    font = ImageFont.truetype(self.FONT_PATH, new_font_size)
                except IOError:
                    font = ImageFont.load_default()
                
                # Пересчитываем размеры строк с новым шрифтом
                line_heights = []
                line_widths = []
                for line in lines:
                    try:
                        text_bbox = draw.textbbox((0, 0), line, font=font)
                        width = text_bbox[2] - text_bbox[0]
                        height = text_bbox[3] - text_bbox[1]
                    except AttributeError:
                        width, height = draw.textsize(line, font=font)
                    line_widths.append(width)
                    line_heights.append(height)
            
            # Общая высота всего текста с учетом межстрочного интервала
            line_spacing = int(font_size * 0.3)  # Межстрочный интервал 30% от размера шрифта
            total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
            
            # Проверяем, если текст слишком высокий для контейнера
            if total_height > container_height:
                # Уменьшаем размер шрифта, чтобы текст поместился по высоте
                scale_factor = container_height / total_height * 0.95  # 5% запас
                new_font_size = int(font_size * scale_factor)
                try:
                    font = ImageFont.truetype(self.FONT_PATH, new_font_size)
                except IOError:
                    font = ImageFont.load_default()
                
                # Пересчитываем размеры строк с новым шрифтом
                line_heights = []
                line_widths = []
                for line in lines:
                    try:
                        text_bbox = draw.textbbox((0, 0), line, font=font)
                        width = text_bbox[2] - text_bbox[0]
                        height = text_bbox[3] - text_bbox[1]
                    except AttributeError:
                        width, height = draw.textsize(line, font=font)
                    line_widths.append(width)
                    line_heights.append(height)
                
                line_spacing = int(new_font_size * 0.3)
                total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
            
            # Вычисляем начальную позицию Y внутри контейнера
            if vertical_position == "top":
                text_start_y = container_top
            elif vertical_position == "bottom":
                text_start_y = container_top + container_height - total_height
            else:  # middle
                text_start_y = container_top + (container_height - total_height) // 2
            
            # Рисуем каждую строку текста с учетом выравнивания
            current_y = text_start_y
            for i, line in enumerate(lines):
                if text_align == "left":
                    x = container_left
                elif text_align == "right":
                    x = container_left + container_width - line_widths[i]
                else:  # center
                    x = container_left + (container_width - line_widths[i]) // 2
                
                # Рисуем строку текста
                draw.text((x, current_y), line, fill=rgb_color, font=font)
                
                # Перемещаем координату Y для следующей строки
                current_y += line_heights[i] + line_spacing
            
            # Для отладки - рисуем границу контейнера
            # draw.rectangle([(container_left, container_top), 
            #                 (container_left + container_width, container_top + container_height)], 
            #                outline=(255, 0, 0))
            
            # Сохраняем изображение в буфер памяти
            img_byte_arr = io.BytesIO()
            bg_image.save(img_byte_arr, format='JPEG', quality=95)
            img_byte_arr.seek(0)  # Возвращаем указатель в начало файла
            
            # Возвращаем изображение напрямую
            return Response(
                content=img_byte_arr.getvalue(),
                media_type="image/jpeg",
                headers={"Content-Disposition": "inline; filename=riddle.jpg"}
            )
            
        except Exception as e:
            logger.error(f"Ошибка при создании загадки: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": str(e)}
            )
    
    def register(self, admin: Admin) -> None:
        """Регистрирует маршруты для создания загадок."""
        admin.app.get("/admin/riddle")(require_organizer_role(self.get_riddle_page))
        admin.app.get("/admin/riddle/")(require_organizer_role(self.get_riddle_page))
        admin.app.post("/admin/riddle/generate")(require_organizer_role(self.generate_riddle))


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Middleware для аутентификации в админке, дающее доступ только пользователям с ролью organizer."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Пути, которые доступны без аутентификации
        self.public_paths = {"/admin/statics", "/registration"}
    
    def is_public_path(self, path: str) -> bool:
        """Проверяет, является ли путь публичным."""
        return any(path.startswith(public_path) for public_path in self.public_paths)

    async def get_user(self, request: Request) -> Optional[Any]:
        """Получает пользователя из запроса, напрямую обращаясь к БД."""
        # Получаем токен сессии из запроса
        session_token = get_access_token(request)
        if not session_token:
            logger.debug("Токен сессии не найден в запросе")
            return None
        
        # Получаем сессию пользователя из БД
        async with AsyncSession(engine) as session:
            session_dao = SessionDAO(session)
            user_session = await session_dao.get_session(session_token)
        
            # Проверяем существование и валидность сессии
            if not user_session:
                logger.debug("Недействительная или не найденная сессия")
                return None
            
            # Получаем пользователя
            users_dao = UsersDAO(session)
            user = await users_dao.find_one_or_none_by_id(user_session.user_id)
            
            return user

    async def dispatch(self, request: Request, call_next):
        # Игнорируем запросы не к админке
        if not request.url.path.startswith("/admin"):
            return await call_next(request)
            
        # Разрешаем доступ к публичным путям
        if self.is_public_path(request.url.path):
            response = await call_next(request)
            # Добавляем кеширование для статических файлов
            if request.url.path.startswith("/admin/statics"):
                response.headers["Cache-Control"] = "public, max-age=3600"

                if not DEBUG:   
                    # Добавляем заголовок для обеспечения безопасности контента
                    response.headers["Content-Security-Policy"] = "upgrade-insecure-requests"
            return response
            
        # Получаем и проверяем пользователя
        user = await self.get_user(request)
        
        if not user:
            logger.debug("Пользователь не аутентифицирован при доступе к админке")
            response = RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response
        
        # Проверяем роль пользователя
        if not user.role or user.role.name != "organizer":
            logger.debug(f"Попытка доступа к админке пользователем с ролью {user.role.name if user.role else 'None'}")
            response = RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response
            
        # Сохраняем пользователя в запросе для использования в представлениях
        request.scope["user"] = user
        
        # Добавляем заголовок для обеспечения безопасности контента
        response = await call_next(request)
        if not DEBUG:
            response.headers["Content-Security-Policy"] = "upgrade-insecure-requests"
        return response


def require_organizer_role(func: Callable[..., T]) -> Callable[..., T]:
    """Декоратор для проверки роли организатора."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = request.scope.get("user")
        if not user or not hasattr(user, "role") or user.role.name != "organizer":
            response = RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return await func(request, *args, **kwargs)
    return wrapper


def init_admin(app: FastAPI, base_url: str = "/admin") -> Admin:
    """Инициализирует админ-панель с проверкой прав доступа."""
    
    # Создаем экземпляр админки
    admin = Admin(app, engine, base_url=base_url)
    
    # Обработчики для корневого пути с обоими вариантами (со слешем и без)
    @admin.app.get(f"{base_url}")
    @admin.app.get(f"{base_url}/")
    async def redirect_to_dashboard(request: Request):
        """Перенаправляет на панель управления."""
        return RedirectResponse(url="/admin/")
    
    # Добавляем специальный обработчик для /admin/database
    @admin.app.get(f"{base_url}/database")
    async def redirect_to_database(request: Request):
        """Перенаправляет на страницу управления базой данных."""
        return RedirectResponse(url=f"{base_url}/database/", status_code=status.HTTP_302_FOUND)
    
    # Добавляем API-метод для получения статистики регистраций
    @admin.app.get("/api/auth/stats/registrations")
    async def get_registrations_data(request: Request):
        """Возвращает данные о регистрациях пользователей."""
        # Проверяем роль пользователя
        user = request.scope.get("user")
        if not user or user.role.name != "organizer":
            return JSONResponse(
                content={"ok": False, "message": "Недостаточно прав для просмотра статистики"},
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Перенаправляем запрос на обработчик в auth router
            from app.auth.router import get_registration_stats
            from app.dependencies.auth_dep import get_session_with_commit
            
            # Используем зависимость для получения сессии
            session = await get_session_with_commit(request)
            
            # Вызываем обработчик из auth router
            return await get_registration_stats(session=session, user=user)
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
            return JSONResponse(
                content={"ok": False, "message": "Внутренняя ошибка сервера"},
                status_code=500
            )
        
    # Применяем middleware для аутентификации
    admin.app.add_middleware(AdminAuthMiddleware)
    
    # Добавляем панель управления
    dashboard_view = AdminDashboardView()
    dashboard_view.register(admin)
    
    # Добавляем страницу создания загадок
    riddle_view = AdminRiddleView()
    riddle_view.register(admin)
    
    # Автоматически регистрируем все классы ModelView из модуля views
    for name, view in vars(views).items():
        if name.endswith('Admin') and hasattr(view, 'model'):
            admin.add_view(view)
    
    return admin
