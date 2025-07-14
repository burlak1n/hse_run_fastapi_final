from sqladmin import Admin, ModelView, BaseView
from fastapi import FastAPI, status, Form
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse, JSONResponse, Response
from starlette.types import ASGIApp
from sqlalchemy.ext.asyncio import AsyncSession
from functools import wraps
from typing import Any, Optional, Callable, TypeVar
import os
from PIL import Image, ImageDraw, ImageFont
import io
from sqlalchemy.orm import selectinload

from app.config import DEBUG
from app.dao.database import engine
from app.cms import views
from app.dependencies.auth_dep import get_access_token
from app.dependencies.template_dep import get_templates
from app.auth.dao import UsersDAO, SessionDAO
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
    icon = "fa-solid fa-image"
    
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


class AdminProgramView(AdminPage):
    """Представление для работы с картой программы."""
    name = "Программа"
    icon = "fa-solid fa-map"
    
    async def get_program_page(self, request: Request) -> HTMLResponse:
        """Отображает страницу с картой программы."""
        from app.quest.dao import QuestionsDAO
        from sqlalchemy.ext.asyncio import AsyncSession
        
        user = request.scope.get("user")
        
        # Получаем список вопросов для выпадающего списка
        async with AsyncSession(engine) as session:
            questions_dao = QuestionsDAO(session)
            questions = await questions_dao.get_all_questions()
        
        return templates.TemplateResponse(
            "admin/program.html",
            {"request": request, "user": user, "questions": questions}
        )
    
    async def get_map_markers(self, request: Request) -> JSONResponse:
        """Возвращает все маркеры карты в формате JSON."""
        # В будущем здесь будет логика получения маркеров из БД
        # Пока возвращаем пустой список
        return JSONResponse({
            "ok": True,
            "data": {
                "markers": []
            }
        })
    
    async def save_map_markers(self, request: Request) -> JSONResponse:
        """Сохраняет маркеры карты."""
        try:
            data = await request.json()
            markers = data.get("markers", [])
            
            # В будущем здесь будет логика сохранения маркеров в БД
            # Пока просто возвращаем те же данные
            
            return JSONResponse({
                "ok": True,
                "message": "Маркеры успешно сохранены",
                "data": {
                    "markers": markers
                }
            })
        except Exception as e:
            logger.error(f"Ошибка при сохранении маркеров: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при сохранении маркеров: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    async def get_program_stats(self, request: Request) -> JSONResponse:
        """Возвращает статистику по программе мероприятия."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.auth.dao import UsersDAO # Убрали ProgramDAO, т.к. запросы к Program делаем напрямую
        from sqlalchemy import func, select
        from app.auth.models import Program, User, Command, CommandsUser

        try:
            async with AsyncSession(engine) as session:
                users_dao = UsersDAO(session)
                
                total_users = await users_dao.count_all_users()
                
                active_users_query = select(
                    func.count(func.distinct(Program.user_id))
                )
                active_users_result = await session.execute(active_users_query)
                active_users = active_users_result.scalar_one_or_none() or 0

                # Запрос для получения баллов команд (остается)
                team_scores_query = select(
                    Command.name.label('team_name'),
                    func.sum(Program.score).label('total_score')
                ).join(
                    CommandsUser, Command.id == CommandsUser.command_id
                ).join(
                    Program, CommandsUser.user_id == Program.user_id
                ).group_by(
                    Command.id, Command.name
                ).order_by(
                    func.sum(Program.score).desc()
                )
                team_scores_result = await session.execute(team_scores_query)
                team_scores_data = team_scores_result.all()
                team_scores = [
                    {"name": row.team_name, "score": float(row.total_score)}
                    for row in team_scores_data
                ]
                
                # Запрос для получения ID топ-10 пользователей по сумме баллов
                top_user_ids_query = select(
                    Program.user_id
                ).group_by(
                    Program.user_id
                ).order_by(
                    func.sum(Program.score).desc()
                ).limit(10)
                
                top_user_ids_result = await session.execute(top_user_ids_query)
                top_user_ids = [row.user_id for row in top_user_ids_result.all()]
                
                # Собираем данные о пользователях и их транзакциях
                top_users_with_transactions = []
                if top_user_ids:
                    # Получаем информацию о пользователях одним запросом
                    users_info_query = select(User).where(User.id.in_(top_user_ids))
                    users_info_result = await session.execute(users_info_query)
                    users_map = {user.id: user for user in users_info_result.scalars().all()}

                    # Получаем команды пользователей (можно оптимизировать, но пока оставим так)
                    commands_map = {}
                    for user_id in top_user_ids:
                        command = await users_dao.find_user_command_in_event(user_id)
                        commands_map[user_id] = command

                    # Получаем все транзакции для этих пользователей одним запросом
                    transactions_query = select(Program).where(Program.user_id.in_(top_user_ids)).order_by(Program.created_at.desc())
                    transactions_result = await session.execute(transactions_query)
                    all_transactions = transactions_result.scalars().all()

                    # Группируем транзакции по user_id
                    user_transactions_map = {}
                    for tx in all_transactions:
                        if tx.user_id not in user_transactions_map:
                            user_transactions_map[tx.user_id] = []
                        user_transactions_map[tx.user_id].append({
                            # "id": tx.id, # ID транзакции пока не нужен
                            "score": tx.score,
                            "comment": tx.comment or "",
                            "created_at": tx.created_at.isoformat() if tx.created_at else None
                        })
                    
                    # Формируем итоговый список top_users
                    for user_id in top_user_ids:
                        user = users_map.get(user_id)
                        command = commands_map.get(user_id)
                        if user:
                            top_users_with_transactions.append({
                                "id": user_id,
                                "name": user.full_name or user.telegram_username or f"Пользователь #{user_id}",
                                "team": command.name if command else None,
                                "transactions": user_transactions_map.get(user_id, []) # Список транзакций пользователя
                            })
                
                return JSONResponse({
                    "ok": True,
                    "data": {
                        "total_users": total_users,
                        "top_users": top_users_with_transactions, # Возвращаем пользователей с транзакциями
                        "people_on_site": active_users,
                        "team_scores": team_scores
                    }
                })
        except Exception as e:
            logger.error(f"Ошибка при получении статистики программы: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при получении статистики: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    async def get_user_program_stats(self, request: Request, user_id: int) -> JSONResponse:
        """Возвращает статистику по программе для конкретного пользователя."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.auth.dao import ProgramDAO, UsersDAO
        
        try:
            async with AsyncSession(engine) as session:
                program_dao = ProgramDAO(session)
                users_dao = UsersDAO(session)
                
                # Получаем пользователя
                user = await users_dao.find_one_by_id(user_id)
                if not user:
                    return JSONResponse({
                        "ok": False,
                        "message": "Пользователь не найден"
                    }, status_code=status.HTTP_404_NOT_FOUND)
                
                # Получаем общую сумму баллов пользователя
                total_score = await program_dao.get_total_score(user_id)
                
                # Получаем историю начисления баллов
                history = await program_dao.get_score_history(user_id)
                
                # Преобразуем историю в удобный формат
                history_data = []
                for record in history:
                    history_data.append({
                        "id": record.id,
                        "score": record.score,
                        "comment": record.comment,
                        "created_at": record.created_at.isoformat() if record.created_at else None
                    })
                
                # Получаем команду пользователя, если есть
                command = await users_dao.find_user_command_in_event(user_id)
                command_data = None
                if command:
                    command_data = {
                        "id": command.id,
                        "name": command.name,
                        "participants_count": len(command.users)
                    }
                
                return JSONResponse({
                    "ok": True,
                    "data": {
                        "user": {
                            "id": user.id,
                            "full_name": user.full_name,
                            "telegram_username": user.telegram_username,
                            "role": user.role.name if user.role else None
                        },
                        "program": {
                            "total_score": float(total_score),
                            "history": history_data
                        },
                        "command": command_data
                    }
                })
        except Exception as e:
            logger.error(f"Ошибка при получении статистики пользователя {user_id}: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при получении статистики: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    async def get_top_users_stats(self, request: Request) -> JSONResponse:
        """Возвращает список пользователей с наибольшим количеством баллов."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.auth.dao import ProgramDAO, UsersDAO
        from sqlalchemy import select, func
        from app.auth.models import Program, User
        
        # Получаем лимит из параметров запроса
        limit = request.query_params.get("limit", "10")
        try:
            limit = int(limit)
            if limit < 1 or limit > 100:
                limit = 10
        except ValueError:
            limit = 10
                
        try:
            async with AsyncSession(engine) as session:
                # Создаем запрос для получения пользователей с суммой баллов
                query = select(
                    Program.user_id,
                    func.sum(Program.score).label('total_score')
                ).group_by(
                    Program.user_id
                ).order_by(
                    func.sum(Program.score).desc()
                ).limit(limit)
                
                result = await session.execute(query)
                top_users_scores = result.all()
                
                # Получаем информацию о пользователях
                top_users = []
                for user_score in top_users_scores:
                    user_id = user_score.user_id
                    score = user_score.total_score
                    
                    # Получаем данные пользователя
                    user_query = select(User).where(User.id == user_id)
                    user_result = await session.execute(user_query)
                    user = user_result.scalar_one_or_none()
                    
                    if user:
                        # Получаем команду пользователя
                        from app.auth.dao import UsersDAO
                        users_dao = UsersDAO(session)
                        command = await users_dao.find_user_command_in_event(user_id)
                        
                        top_users.append({
                            "id": user_id,
                            "full_name": user.full_name,
                            "telegram_username": user.telegram_username,
                            "role": user.role.name if user.role else None,
                            "score": float(score),
                            "command": {
                                "id": command.id if command else None,
                                "name": command.name if command else None
                            }
                        })
                
                return JSONResponse({
                    "ok": True,
                    "data": {
                        "top_users": top_users,
                        "limit": limit
                    }
                })
        except Exception as e:
            logger.error(f"Ошибка при получении топ пользователей: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при получении статистики: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    async def get_user_transactions(self, request: Request, user_id: int) -> JSONResponse:
        """Возвращает историю транзакций пользователя."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.auth.dao import ProgramDAO, UsersDAO
        
        try:
            async with AsyncSession(engine) as session:
                program_dao = ProgramDAO(session)
                users_dao = UsersDAO(session)
                
                # Получаем пользователя
                user = await users_dao.find_one_by_id(user_id)
                if not user:
                    return JSONResponse({
                        "ok": False,
                        "message": "Пользователь не найден"
                    }, status_code=status.HTTP_404_NOT_FOUND)
                
                # Получаем историю баллов пользователя
                history = await program_dao.get_score_history(user_id)
                
                # Преобразуем историю в формат транзакций
                transactions = []
                for record in history:
                    transaction_type = "credit" if record.score >= 0 else "debit"
                    transactions.append({
                        "id": record.id,
                        "date": record.created_at.isoformat() if record.created_at else None,
                        "description": record.comment or "Нет описания",
                        "amount": abs(record.score),
                        "type": transaction_type
                    })
                
                return JSONResponse({
                    "ok": True,
                    "transactions": transactions
                })
        except Exception as e:
            logger.error(f"Ошибка при получении транзакций пользователя {user_id}: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при получении транзакций: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def register(self, admin: Admin) -> None:
        """Регистрирует маршруты для работы с картой программы."""
        admin.app.get("/admin/program")(require_organizer_role(self.get_program_page))
        admin.app.get("/admin/program/")(require_organizer_role(self.get_program_page))
        admin.app.get("/admin/program/get")(require_organizer_role(self.get_map_markers))
        admin.app.post("/admin/program/save")(require_organizer_role(self.save_map_markers))
        admin.app.get("/admin/program/stats")(require_organizer_role(self.get_program_stats))
        admin.app.get("/admin/program/user/{user_id}/stats")(require_organizer_role(self.get_user_program_stats))
        admin.app.get("/admin/program/top_users")(require_organizer_role(self.get_top_users_stats))
        admin.app.get("/admin/program/user/{user_id}/transactions")(require_organizer_role(self.get_user_transactions))


class AdminQuestView(AdminPage):
    """Представление для статистики по квесту."""
    name = "Квест"
    icon = "fa-solid fa-list-check"

    async def get_quest_page(self, request: Request) -> HTMLResponse:
        """Отображает страницу статистики квеста."""
        user = request.scope.get("user")
        return templates.TemplateResponse(
            "admin/quest.html",
            {"request": request, "user": user}
        )

    async def get_quest_stats(self, request: Request) -> JSONResponse:
        """Возвращает статистику по попыткам в квесте."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.quest.dao import AttemptsDAO  # Предполагаем, что такой DAO есть
        from app.auth.dao import UsersDAO # Для информации о пользователях
        from sqlalchemy import func, select
        from app.quest.models import Attempt, AttemptType, Question, Block # Добавляем Block для языка
        from app.auth.models import User, Command, CommandsUser, Language # Добавляем Language для языка

        try:
            async with AsyncSession(engine) as session:
                attempts_dao = AttemptsDAO(session)
                users_dao = UsersDAO(session)

                # Пример: Топ пользователей по кол-ву попыток
                top_users_by_attempts_query = select(
                    Attempt.user_id,
                    func.count(Attempt.id).label('attempts_count')
                ).group_by(
                    Attempt.user_id
                ).order_by(
                    func.count(Attempt.id).desc()
                ) # Увеличим лимит, чтобы видеть больше пользователей

                top_users_result = await session.execute(top_users_by_attempts_query)
                top_attempts_rows = top_users_result.all()
                
                top_users_data = []
                user_ids = [row.user_id for row in top_attempts_rows]
                
                if user_ids:
                    # Получаем информацию о пользователях
                    users_info_query = select(User).options(selectinload(User.role)).where(User.id.in_(user_ids))
                    users_info_result = await session.execute(users_info_query)
                    users_map = {user.id: user for user in users_info_result.unique().scalars().all()}

                    # Получаем связки CommandsUser и ЗАГРУЖАЕМ команды с языком И пользователями
                    commands_user_query = select(CommandsUser).options(
                        selectinload(CommandsUser.command).selectinload(Command.language),
                        selectinload(CommandsUser.command).selectinload(Command.users) # Загружаем пользователей команды
                    ).where(CommandsUser.user_id.in_(user_ids))
                    commands_user_result = await session.execute(commands_user_query)
                    
                    commands_map = {}
                    # Создаем карту user_id -> {id, name, language_name, participants_count}
                    for cu in commands_user_result.unique().scalars().all():
                        command_data = None
                        if cu.command:
                            command_data = {
                                "id": cu.command.id,
                                "name": cu.command.name,
                                "language": cu.command.language.name if cu.command.language else None,
                                "participants_count": len(cu.command.users) # Считаем участников
                            }
                        commands_map[cu.user_id] = command_data
                        
                    # Убедимся, что все user_id есть в карте, даже если у них нет команды
                    for user_id in user_ids:
                        if user_id not in commands_map:
                            commands_map[user_id] = None

                    # Получаем ВСЕ попытки для этих пользователей одним запросом
                    all_attempts_query = select(Attempt).options(
                        selectinload(Attempt.attempt_type), # Загружаем тип попытки
                        selectinload(Attempt.question)     # Загружаем вопрос
                    ).where(Attempt.user_id.in_(user_ids)).order_by(Attempt.created_at.desc())
                    
                    all_attempts_result = await session.execute(all_attempts_query)
                    # Используем unique() чтобы избежать дубликатов из-за selectinload
                    all_attempts = all_attempts_result.unique().scalars().all()
                    
                    # Группируем попытки по пользователям и считаем баллы/монеты
                    user_attempts_map = {user_id: [] for user_id in user_ids}
                    user_scores_map = {user_id: {"score": 0, "money": 0} for user_id in user_ids}
                    
                    for attempt in all_attempts:
                        if attempt.user_id in user_attempts_map:
                            attempt_data = {
                                "id": attempt.id,
                                "text": attempt.attempt_text,
                                "is_true": attempt.is_true,
                                "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
                                "type_name": attempt.attempt_type.name if attempt.attempt_type else "Неизвестный тип",
                                "score": attempt.attempt_type.score if attempt.attempt_type else 0,
                                "money": attempt.attempt_type.money if attempt.attempt_type else 0,
                                "question_id": attempt.question_id,
                                "question_title": attempt.question.title if attempt.question else None
                            }
                            user_attempts_map[attempt.user_id].append(attempt_data)
                            
                            # Считаем итоговые баллы/монеты пользователя
                            if attempt.is_true and attempt.attempt_type:
                                user_scores_map[attempt.user_id]["score"] += attempt.attempt_type.score
                                user_scores_map[attempt.user_id]["money"] += attempt.attempt_type.money

                    # Формируем итоговый список пользователей
                    for user_id in user_ids:
                        user = users_map.get(user_id)
                        command_data = commands_map.get(user_id)
                        if user:
                            user_data = {
                                # Данные пользователя (как раньше)
                                "id": user_id,
                                "full_name": user.full_name,
                                "telegram_username": user.telegram_username,
                                # Данные команды (как раньше)
                                "team": command_data["name"] if command_data else None,
                                "team_language": command_data["language"] if command_data else None,
                                "team_participants_count": command_data["participants_count"] if command_data else None, # Добавляем число участников
                                "attempts": user_attempts_map[user_id] # Список всех попыток
                            }
                            top_users_data.append(user_data)
                
                # Сортируем итоговый список пользователей по имени (или другому критерию)
                top_users_data.sort(key=lambda x: x.get('full_name', '').lower())

                # Получаем все вопросы, их геоданные и язык
                all_questions_query = select(Question).options(
                    selectinload(Question.block).selectinload(Block.language) # Загружаем блок и язык
                )
                all_questions_result = await session.execute(all_questions_query)
                all_question_locations = {
                    q.id: {
                        "title": q.title, 
                        "geo_answered": q.geo_answered, 
                        "language": q.block.language.name if q.block and q.block.language else None
                    }
                    for q in all_questions_result.unique().scalars().all() # Используем unique().scalars()
                }

                return JSONResponse({
                    "ok": True,
                    "data": {
                        "top_users_by_attempts": top_users_data,
                        "all_question_locations": all_question_locations
                    }
                })

        except Exception as e:
            logger.error(f"Ошибка при получении статистики квеста: {e}", exc_info=True)
            return JSONResponse({
                "ok": False,
                "message": f"Ошибка при получении статистики квеста: {str(e)}"
            }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def register(self, admin: Admin) -> None:
        """Регистрирует маршруты для статистики квеста."""
        admin.app.get("/admin/quest")(require_organizer_role(self.get_quest_page))
        admin.app.get("/admin/quest/")(require_organizer_role(self.get_quest_page))
        admin.app.get("/admin/quest/stats")(require_organizer_role(self.get_quest_stats))


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
            if not DEBUG:   
                # Добавляем заголовок для обеспечения безопасности контента
                response.headers["Content-Security-Policy"] = "upgrade-insecure-requests"
            return response
            
        # Получаем и проверяем пользователя
        user = await self.get_user(request)
        
        if not user:
            logger.debug("Пользователь не аутентифицирован при доступе к админке")
            response = RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
            return response
        
        # Проверяем роль пользователя
        if not user.role or user.role.name != "organizer":
            logger.debug(f"Попытка доступа к админке пользователем с ролью {user.role.name if user.role else 'None'}")
            response = RedirectResponse(url="/registration", status_code=status.HTTP_303_SEE_OTHER)
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
    admin_dashboard = AdminDashboardView()
    admin_dashboard.register(admin)
    
    # Добавляем страницу создания загадок
    riddle_view = AdminRiddleView()
    riddle_view.register(admin)
    
    # Добавляем страницу работы с картой программы
    program_view = AdminProgramView()
    program_view.register(admin)
    
    # Добавляем страницу статистики квеста
    quest_view = AdminQuestView()
    quest_view.register(admin)
    
    # Автоматически регистрируем все классы ModelView из модуля views
    for name, view in vars(views).items():
        if name.endswith('Admin') and hasattr(view, 'model'):
            admin.add_view(view)
    return admin
