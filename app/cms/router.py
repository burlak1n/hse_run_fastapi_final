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

from app.dao.database import engine
from app.cms import views
from app.dependencies.auth_dep import get_access_token
from app.auth.dao import UsersDAO, SessionDAO
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
            <link rel="stylesheet" href="/admin/statics/css/sqladmin.css">
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
                    <a href="/admin/database" class="btn">Управление БД</a>
                    <a href="/admin/riddle" class="btn">Создать загадку</a>
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
        try:
            # Получаем токен сессии из запроса
            session_token = get_access_token(request)
            if not session_token:
                return None
        except Exception:
            logger.debug("Не удалось получить токен доступа")
            return None
        
        # Получаем сессию пользователя из БД
        async with AsyncSession(engine) as session:
            session_dao = SessionDAO(session)
            user_session = await session_dao.get_session(session_token)
        
            # Проверяем существование и валидность сессии
            if not user_session or not user_session.is_valid():
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
            return response
            
        # Получаем и проверяем пользователя
        user = await self.get_user(request)
        
        if not user:
            logger.debug("Пользователь не аутентифицирован при доступе к админке")
            return RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
        
        # Проверяем роль пользователя
        if not user.role or user.role.name != "organizer":
            logger.debug(f"Попытка доступа к админке пользователем с ролью {user.role.name if user.role else 'None'}")
            return RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
            
        # Сохраняем пользователя в запросе для использования в представлениях
        request.scope["user"] = user
        
        return await call_next(request)


def require_organizer_role(func: Callable[..., T]) -> Callable[..., T]:
    """Декоратор для проверки роли организатора."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = request.scope.get("user")
        if not user or not hasattr(user, "role") or user.role.name != "organizer":
            return RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
        return await func(request, *args, **kwargs)
    return wrapper


def init_admin(app: FastAPI, base_url: str = "/admin") -> Admin:
    """Инициализирует админ-панель с проверкой прав доступа."""
    
    # Создаем экземпляр админки
    admin = Admin(app, engine, base_url=base_url)
    
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
