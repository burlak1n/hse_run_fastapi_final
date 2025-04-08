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
from app.auth.dao import UsersDAO, SessionDAO
from app.auth.models import User
from app.logger import logger

# Определяем возвращаемый тип для декораторов
T = TypeVar('T')

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
        content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Панель управления</title>
            <style>
                .dashboard-container {{
                    padding: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                .card {{
                    background: #fff;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    padding: 20px;
                    margin-bottom: 20px;
                }}
                .card h2 {{
                    margin-top: 0;
                    color: #333;
                }}
                .btn {{
                    display: inline-block;
                    padding: 8px 16px;
                    background: #4CAF50;
                    color: white;
                    border-radius: 4px;
                    text-decoration: none;
                    margin-top: 10px;
                }}
                .btn:hover {{
                    background: #45a049;
                }}
            </style>
        </head>
        <body>
            <div class="dashboard-container">
                <div class="card">
                    <h2>Добро пожаловать, {user.full_name if user else 'Администратор'}!</h2>
                    <p>У вас есть доступ к управлению системой как <strong>организатор</strong>.</p>
                </div>
                
                <div class="card">

                    <h2>Быстрые действия</h2>
                    <a href="/admin/database/" class="btn">Управление БД</a>
                    <a href="/admin/riddle" class="btn">Создать загадку</a>
                    <a href="/admin/statistics/" class="btn">Статистика команд</a>
                    <br><br>
                    <a href="/quest" class="btn" style="background-color: #808080;">Вернуться на квест</a>
                </div>
                
                <div class="card">
                    <h2>Статистика системы</h2>
                    <p>Здесь будет отображаться статистика работы системы.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=content)

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
        content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Создание загадки</title>
            <link rel="stylesheet" href="/admin/statics/css/sqladmin.css">
            <style>
                .container {
                    max-width: 800px;
                    margin: 20px auto;
                    padding: 20px;
                    background: #fff;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .form-group {
                    margin-bottom: 15px;
                }
                label {
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                }
                textarea {
                    width: 100%;
                    height: 150px;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    resize: vertical;
                }
                button {
                    padding: 10px 15px;
                    background: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                .preview {
                    margin-top: 20px;
                    border: 1px dashed #ccc;
                    padding: 10px;
                    text-align: center;
                }
                .preview img {
                    max-width: 100%;
                    height: auto;
                }
                #result-container {
                    display: none;
                    margin-top: 20px;
                }
                #download-btn {
                    display: block;
                    margin: 10px auto;
                    background: #007bff;
                }
                .align-options {
                    display: flex;
                    gap: 10px;
                    margin-bottom: 15px;
                }
                .align-option {
                    flex: 1;
                    text-align: center;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    cursor: pointer;
                }
                .align-option.selected {
                    background-color: #e0f7fa;
                    border-color: #4CAF50;
                }
                .align-option img {
                    width: 20px;
                    height: 20px;
                    margin-bottom: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/admin" style="display: inline-block; margin-bottom: 20px; padding: 8px 16px; background-color: #f0f0f0; border-radius: 4px; text-decoration: none; color: #333;">← Назад</a>
                <h1>Создание загадки</h1>
                <form id="riddle-form">
                    <div class="form-group">
                        <label for="riddle-text">Текст загадки:</label>
                        <textarea id="riddle-text" name="text" placeholder="Введите текст загадки..." required></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label>Выравнивание текста:</label>
                        <div class="align-options">
                            <div class="align-option selected" data-align="left">
                                <span>По левому краю</span>
                            </div>
                            <div class="align-option" data-align="center">
                                <span>По центру</span>
                            </div>
                            <div class="align-option" data-align="right">
                                <span>По правому краю</span>
                            </div>
                        </div>
                        <input type="hidden" id="text-align" name="text_align" value="left">
                    </div>
                    
                    <div class="form-group">
                        <label for="font-size">Размер шрифта:</label>
                        <input type="number" id="font-size" name="font_size" value="36" min="12" max="72">
                    </div>
                    
                    <div class="form-group">
                        <label for="text-color">Цвет текста:</label>
                        <input type="color" id="text-color" name="text_color" value="#ffffff">
                    </div>
                    
                    <div class="form-group">
                        <label for="vertical-position">Вертикальное положение:</label>
                        <select id="vertical-position" name="vertical_position">
                            <option value="top">Сверху</option>
                            <option value="middle" selected>Посередине</option>
                            <option value="bottom">Снизу</option>
                        </select>
                    </div>
                    
                    <button type="submit">Создать загадку</button>
                </form>
                
                <div id="result-container">
                    <h2>Результат:</h2>
                    <div class="preview">
                        <img id="result-image" src="" alt="Загадка">
                    </div>
                    <a id="download-btn" href="#" class="button" download="riddle.jpg">Скачать изображение</a>
                </div>
            </div>
            
            <script>
                // Обработка выбора выравнивания
                document.querySelectorAll('.align-option').forEach(option => {
                    option.addEventListener('click', () => {
                        // Снимаем выделение со всех опций
                        document.querySelectorAll('.align-option').forEach(opt => {
                            opt.classList.remove('selected');
                        });
                        
                        // Выделяем выбранную опцию
                        option.classList.add('selected');
                        
                        // Обновляем скрытое поле
                        document.getElementById('text-align').value = option.dataset.align;
                    });
                });
                
                // Обработка отправки формы
                document.getElementById('riddle-form').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    const formData = new FormData();
                    formData.append('text', document.getElementById('riddle-text').value);
                    formData.append('font_size', document.getElementById('font-size').value);
                    formData.append('text_color', document.getElementById('text-color').value);
                    formData.append('text_align', document.getElementById('text-align').value);
                    formData.append('vertical_position', document.getElementById('vertical-position').value);
                    
                    try {
                        const response = await fetch('/admin/riddle/generate', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (response.ok) {
                            const blob = await response.blob();
                            const imageUrl = URL.createObjectURL(blob);
                            
                            document.getElementById('result-image').src = imageUrl;
                            document.getElementById('download-btn').href = imageUrl;
                            document.getElementById('result-container').style.display = 'block';
                        } else {
                            alert('Ошибка при создании загадки');
                        }
                    } catch (error) {
                        console.error('Ошибка:', error);
                        alert('Произошла ошибка при отправке запроса');
                    }
                });
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=content)
    
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


class AdminStatsView(AdminPage):
    """Представление для отображения статистик системы."""
    name = "Статистика"
    icon = "fa-solid fa-chart-line"
    
    async def get_stats_page(self, request: Request) -> HTMLResponse:
        """Отображает страницу статистики."""
        content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Статистика системы</title>
            <link rel="stylesheet" href="/admin/statics/css/sqladmin.css">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                .container {
                    max-width: 1200px;
                    margin: 20px auto;
                    padding: 20px;
                    background: #fff;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .chart-container {
                    width: 100%;
                    height: 400px;
                    margin-top: 20px;
                }
                .nav-tabs {
                    display: flex;
                    border-bottom: 1px solid #dee2e6;
                    margin-bottom: 20px;
                }
                .nav-link {
                    padding: 10px 15px;
                    border: 1px solid transparent;
                    border-top-left-radius: 0.25rem;
                    border-top-right-radius: 0.25rem;
                    margin-right: 5px;
                    cursor: pointer;
                }
                .nav-link.active {
                    color: #495057;
                    background-color: #fff;
                    border-color: #dee2e6 #dee2e6 #fff;
                }
                .tab-content {
                    padding: 20px 0;
                }
                .tab-pane {
                    display: none;
                }
                .tab-pane.active {
                    display: block;
                }
                .btn {
                    display: inline-block;
                    padding: 8px 16px;
                    background: #4CAF50;
                    color: white;
                    border-radius: 4px;
                    text-decoration: none;
                    margin-top: 10px;
                }
                .btn:hover {
                    background: #45a049;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/admin" style="display: inline-block; margin-bottom: 20px; padding: 8px 16px; background-color: #f0f0f0; border-radius: 4px; text-decoration: none; color: #333;">← Назад</a>
                <h1>Статистика системы</h1>
                
                <div class="nav-tabs">
                    <div class="nav-link active" data-tab="registrations">Регистрации</div>
                    <div class="nav-link" data-tab="teams">Команды</div>
                </div>
                
                <div class="tab-content">
                    <div class="tab-pane active" id="registrations">
                        <h2>Статистика регистраций пользователей</h2>
                        <div class="chart-container">
                            <canvas id="registrationsChart"></canvas>
                        </div>
                    </div>
                    
                    <div class="tab-pane" id="teams">
                        <h2>Статистика команд</h2>
                        <div class="chart-container">
                            <canvas id="teamsChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Получение данных о регистрациях
                async function fetchRegistrationsData() {
                    try {
                        const response = await fetch('/api/auth/stats/registrations');
                        if (!response.ok) {
                            throw new Error('Ошибка при получении данных');
                        }
                        const data = await response.json();
                        if (!data.ok) {
                            throw new Error(data.message || 'Ошибка получения данных');
                        }
                        return data.stats;
                    } catch (error) {
                        console.error('Ошибка:', error);
                        return null;
                    }
                }
                
                // Отображение графика регистраций
                async function renderRegistrationsChart() {
                    const stats = await fetchRegistrationsData();
                    if (!stats) {
                        document.getElementById('registrationsChart').innerHTML = 
                            '<div style="text-align: center; padding: 20px;">Не удалось загрузить данные статистики</div>';
                        return;
                    }
                    
                    // Создаем данные для диаграммы распределения размеров команд
                    const teamSizes = Object.keys(stats.team_distribution).map(size => parseInt(size));
                    const teamCounts = teamSizes.map(size => stats.team_distribution[size]);
                    
                    const ctx = document.getElementById('registrationsChart').getContext('2d');
                    
                    // Создаем диаграмму
                    new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: ['Всего пользователей', 'Активных пользователей', 'Команд', 'Ищущих команду'],
                            datasets: [{
                                label: 'Количество',
                                data: [stats.total_users, stats.active_users, stats.total_teams, stats.users_looking_for_team],
                                backgroundColor: [
                                    'rgba(54, 162, 235, 0.6)',
                                    'rgba(75, 192, 192, 0.6)',
                                    'rgba(255, 159, 64, 0.6)',
                                    'rgba(153, 102, 255, 0.6)'
                                ],
                                borderColor: [
                                    'rgb(54, 162, 235)',
                                    'rgb(75, 192, 192)',
                                    'rgb(255, 159, 64)',
                                    'rgb(153, 102, 255)'
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    ticks: {
                                        precision: 0
                                    }
                                }
                            },
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Общая статистика регистраций'
                                },
                                tooltip: {
                                    callbacks: {
                                        label: function(context) {
                                            return context.raw;
                                        }
                                    }
                                }
                            }
                        }
                    });
                    
                    // Добавляем дополнительную диаграмму для распределения размеров команд
                    const teamDistributionContainer = document.createElement('div');
                    teamDistributionContainer.className = 'chart-container';
                    teamDistributionContainer.style.marginTop = '30px';
                    
                    const teamDistributionCanvas = document.createElement('canvas');
                    teamDistributionCanvas.id = 'teamDistributionChart';
                    teamDistributionContainer.appendChild(teamDistributionCanvas);
                    
                    document.getElementById('registrations').appendChild(teamDistributionContainer);
                    
                    const teamCtx = document.getElementById('teamDistributionChart').getContext('2d');
                    new Chart(teamCtx, {
                        type: 'bar',
                        data: {
                            labels: teamSizes.map(size => `${size} участников`),
                            datasets: [{
                                label: 'Количество команд',
                                data: teamCounts,
                                backgroundColor: 'rgba(255, 159, 64, 0.6)',
                                borderColor: 'rgb(255, 159, 64)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    ticks: {
                                        precision: 0
                                    }
                                }
                            },
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Распределение команд по размеру'
                                }
                            }
                        }
                    });
                    
                    // Добавляем график регистраций по дням
                    if (stats.registrations_by_date && stats.registrations_by_date.length > 0) {
                        const registrationsByDateContainer = document.createElement('div');
                        registrationsByDateContainer.className = 'chart-container';
                        registrationsByDateContainer.style.marginTop = '30px';
                        
                        const registrationsByDateCanvas = document.createElement('canvas');
                        registrationsByDateCanvas.id = 'registrationsByDateChart';
                        registrationsByDateContainer.appendChild(registrationsByDateCanvas);
                        
                        document.getElementById('registrations').appendChild(registrationsByDateContainer);
                        
                        // Подготавливаем данные для графика
                        const dates = stats.registrations_by_date.map(item => item.date);
                        const counts = stats.registrations_by_date.map(item => item.count);
                        
                        // Создаем кумулятивный массив для общего количества регистраций
                        const cumulativeCounts = [];
                        let sum = 0;
                        for (const count of counts) {
                            sum += count;
                            cumulativeCounts.push(sum);
                        }
                        
                        const registrationsByDateCtx = document.getElementById('registrationsByDateChart').getContext('2d');
                        new Chart(registrationsByDateCtx, {
                            type: 'line',
                            data: {
                                labels: dates,
                                datasets: [
                                    {
                                        label: 'Регистрации за день',
                                        data: counts,
                                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                        borderColor: 'rgb(54, 162, 235)',
                                        borderWidth: 2,
                                        tension: 0.1,
                                        yAxisID: 'y'
                                    },
                                    {
                                        label: 'Всего регистраций',
                                        data: cumulativeCounts,
                                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                        borderColor: 'rgb(75, 192, 192)',
                                        borderWidth: 2,
                                        tension: 0.1,
                                        yAxisID: 'y1'
                                    }
                                ]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                scales: {
                                    y: {
                                        beginAtZero: true,
                                        position: 'left',
                                        title: {
                                            display: true,
                                            text: 'Регистрации за день'
                                        },
                                        ticks: {
                                            precision: 0
                                        }
                                    },
                                    y1: {
                                        beginAtZero: true,
                                        position: 'right',
                                        title: {
                                            display: true,
                                            text: 'Всего регистраций'
                                        },
                                        grid: {
                                            drawOnChartArea: false
                                        },
                                        ticks: {
                                            precision: 0
                                        }
                                    }
                                },
                                plugins: {
                                    title: {
                                        display: true,
                                        text: 'Динамика регистраций по дням'
                                    }
                                }
                            }
                        });
                    }
                    
                    // Добавляем информационную панель со статистикой
                    const statsContainer = document.createElement('div');
                    statsContainer.className = 'stats-info';
                    statsContainer.style.marginTop = '30px';
                    statsContainer.style.padding = '15px';
                    statsContainer.style.backgroundColor = '#f8f9fa';
                    statsContainer.style.borderRadius = '5px';
                    
                    const averageTeamSize = stats.average_team_size.toFixed(1);
                    
                    statsContainer.innerHTML = `
                        <h3>Основные показатели</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 20px;">
                            <div style="flex: 1; min-width: 200px;">
                                <p><strong>Всего пользователей:</strong> ${stats.total_users}</p>
                                <p><strong>Активных пользователей:</strong> ${stats.active_users}</p>
                                <p><strong>Процент активации:</strong> ${stats.total_users ? ((stats.active_users / stats.total_users) * 100).toFixed(1) : 0}%</p>
                            </div>
                            <div style="flex: 1; min-width: 200px;">
                                <p><strong>Количество команд:</strong> ${stats.total_teams}</p>
                                <p><strong>Средний размер команды:</strong> ${averageTeamSize}</p>
                                <p><strong>Пользователей, ищущих команду:</strong> ${stats.users_looking_for_team}</p>
                            </div>
                        </div>
                    `;
                    
                    document.getElementById('registrations').appendChild(statsContainer);
                }
                
                // Обработка переключения вкладок
                document.querySelectorAll('.nav-link').forEach(tab => {
                    tab.addEventListener('click', () => {
                        // Убираем активный класс у всех вкладок и контента
                        document.querySelectorAll('.nav-link').forEach(t => t.classList.remove('active'));
                        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
                        
                        // Активируем выбранную вкладку и соответствующий контент
                        tab.classList.add('active');
                        document.getElementById(tab.dataset.tab).classList.add('active');
                    });
                });
                
                // Загрузка данных при загрузке страницы
                document.addEventListener('DOMContentLoaded', () => {
                    renderRegistrationsChart();
                });
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=content)
    
    async def get_registrations_data(self, request: Request) -> JSONResponse:
        """Возвращает данные о регистрациях пользователей по дням."""
        # Получаем сессию для работы с БД
        async with AsyncSession(engine) as session:
            # SQL-запрос для получения количества регистраций по датам
            query = select(
                cast(User.created_at, Date).label('date'),
                func.count(User.id).label('count')
            ).group_by(
                cast(User.created_at, Date)
            ).order_by(
                cast(User.created_at, Date)
            )
            
            # Выполняем запрос
            result = await session.execute(query)
            registrations_by_date = result.all()
            
            # Преобразуем результат запроса в нужный формат
            dates = []
            counts = []
            
            for row in registrations_by_date:
                dates.append(row.date.strftime('%d.%m.%Y'))
                counts.append(row.count)
                
            return JSONResponse(content={
                "dates": dates,
                "counts": counts
            })
    
    def register(self, admin: Admin) -> None:
        """Регистрирует маршруты для статистики."""
        admin.app.get("/admin/statistics")(require_organizer_role(self.get_stats_page))
        admin.app.get("/admin/statistics/")(require_organizer_role(self.get_stats_page))
        admin.app.get("/api/auth/stats/registrations")(require_organizer_role(self.get_registrations_data))


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
    
    # Применяем middleware для аутентификации
    admin.app.add_middleware(AdminAuthMiddleware)
    
    # Добавляем панель управления
    dashboard_view = AdminDashboardView()
    dashboard_view.register(admin)
    
    # Добавляем страницу создания загадок
    riddle_view = AdminRiddleView()
    riddle_view.register(admin)
    
    # Добавляем страницу статистики
    stats_view = AdminStatsView()
    stats_view.register(admin)
    
    # Автоматически регистрируем все классы ModelView из модуля views
    for name, view in vars(views).items():
        if name.endswith('Admin') and hasattr(view, 'model'):
            admin.add_view(view)
    
    return admin
