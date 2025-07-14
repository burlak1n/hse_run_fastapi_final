from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
# Cache imports removed
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import (CommandEdit, CommandInfo,
                              CommandLeaderboardResponse,
                              CompleteRegistrationRequest, ProgramScoreAdd,
                              TelegramAuthData, UpdateProfileRequest)
# Импортируем сервисы
from app.auth.services import (CommandService, EventService, ProgramService,
                               QRService, StatsService, UserService)
from app.auth.utils import set_tokens
from app.dependencies.auth_dep import (get_access_token,
                                       get_current_event_name,
                                       get_current_user)
from app.dependencies.dao_dep import (get_session_with_commit,
                                      get_session_without_commit)
from app.exceptions import (BadRequestException, ForbiddenException,
                            InternalServerErrorException, NotFoundException,
                            TokenExpiredException)
from app.logger import logger

router = APIRouter()

# Аутентификация и авторизация
# ===========================

@router.post("/telegram")
async def telegram_auth(
    user_data: TelegramAuthData,
    session: AsyncSession = Depends(get_session_with_commit)
):
    """Аутентификация через Telegram."""
    try:
        user_service = UserService(session)
        response_content, session_token = await user_service.handle_telegram_auth(user_data)
        
        response = JSONResponse(content=response_content)
        set_tokens(response, session_token) # Используем утилиту для установки кук
        return response
    except Exception as e:
        logger.error(f"Ошибка при аутентификации через Telegram: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при аутентификации.")


@router.post("/complete-registration")
async def complete_registration(
    request: CompleteRegistrationRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Завершение регистрации пользователя."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    try:
        user_service = UserService(session)
        await user_service.complete_registration(user, request)
        return {"ok": True, "message": "Регистрация успешно завершена"}
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при завершении регистрации {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера.")


@router.post("/logout")
async def logout(response: Response):
    # Этот эндпоинт простой, логика остается здесь
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("session_token_alt", path="/")
    return {'message': 'Пользователь успешно вышел из системы'}


# Пользователи и профили
# =====================

@router.get("/me")
async def get_me(
    user_data: Optional[User] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_without_commit) # Используем без коммита, т.к. только чтение
):
    """Получение информации о текущем пользователе."""
    # This log might run even on cache hit if Depends runs first, let's log inside the try block
    # logger.info(f"Processing /me request for user_id: {user_data.id if user_data else 'Unauthorized'}")

    if not user_data:
        # Log unauthorized attempt before raising exception
        logger.warning("Unauthorized attempt to access /me")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    
    # Log entry point *after* authentication check and *before* potential cache hit processing by decorator
    # Note: The exact timing depends on FastAPI/Starlette and fastapi-cache2 interaction.
    # A log *inside* the main logic block is the definitive way to know the function body executed.
    logger.info(f"Executing get_me function body for user_id: {user_data.id} (cache miss or expired)")
    
    try:
        user_service = UserService(session)
        user_profile = await user_service.get_user_profile(user_data.id)
        return user_profile
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при получении профиля пользователя {user_data.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при получении профиля.")


@router.get("/qr")
async def get_me_qr_code(
    user_data: Optional[User] = Depends(get_current_user),
    session_token: Optional[str] = Depends(get_access_token),
    session: AsyncSession = Depends(get_session_without_commit) # Сессия не нужна, но оставим для единообразия
):
    """Генерация QR-кода для текущего пользователя."""
    if not user_data or not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    try:
        # Сервис не требует сессии для этой операции
        qr_service = QRService(session) # Передаем сессию, хотя она может быть не нужна
        qr_info = await qr_service.generate_qr_for_user(user_data, session_token)
        return JSONResponse(qr_info)
    except Exception as e:
        logger.error(f"Ошибка при генерации QR для пользователя {user_data.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при генерации QR-кода.")

class QRVerifyRequest(BaseModel):
    token: str

@router.post("/toggle_looking_for_team")
async def toggle_looking_for_team(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit) # Нужен коммит
):
    """Переключение флага поиска команды."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    
    try:
        user_service = UserService(session)
        new_status = await user_service.toggle_looking_for_team(user.id)
        return {"ok": True, "is_looking_for_friends": new_status}
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при переключении флага is_looking_for_friends для {user.id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при обновлении статуса")

@router.post("/qr/verify")
async def verify_qr(
    request: QRVerifyRequest,
    scanner_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_without_commit) # Только чтение
):
    """Проверка QR-кода и получение информации."""
    if not scanner_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация для проверки QR-кода")
    
    logger.info(f"Начало проверки QR-кода токена {request.token[:5]}... от пользователя {scanner_user.id}")
    
    try:
        qr_service = QRService(session)
        result = await qr_service.verify_qr_and_get_info(scanner_user, request.token)
        return result # Сервис сам формирует нужный ответ
    except TokenExpiredException as e:
        raise HTTPException(status_code=401, detail=str(e))
    except NotFoundException as e:
        # Может возникнуть, если пользователь из токена не найден
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при проверке QR токена {request.token[:5]}...: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при проверке QR.")


# Новый маршрут для присоединения к команде
class JoinTeamRequest(BaseModel):
    token: str  # Токен QR-кода

@router.post("/command/join")
async def join_team(
    request: JoinTeamRequest,
    scanner_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit) # Нужен коммит
):
    """Присоединение к команде через QR-код (по токену)."""
    logger.info(f"Запрос на присоединение к команде от пользователя {scanner_user.id}")
    
    if not scanner_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
        
    try:
        command_service = CommandService(session)
        await command_service.join_command_via_qr(scanner_user, request.token)
        return {"ok": True, "message": "Вы успешно добавлены в команду"}
    except TokenExpiredException as e:
        raise HTTPException(status_code=401, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InternalServerErrorException as e: # Ошибка конфигурации роли
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при присоединении к команде пользователя {scanner_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при присоединении к команде.")


# Управление командами
# ==================

@router.get("/command")
async def get_user_command(
    session: AsyncSession = Depends(get_session_without_commit), # Только чтение
    user: User = Depends(get_current_user)
) -> CommandInfo:
    """Получение информации о команде текущего пользователя."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        command_service = CommandService(session)
        command = await command_service.get_user_command_info(user.id)
        # Валидация в схему Pydantic происходит здесь
        return CommandInfo.model_validate(command)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при получении команды пользователя {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при получении команды.")


@router.post("/command/create")
async def command_create(
    request: CommandEdit,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user),
    event_name: str = Depends(get_current_event_name)
):
    """Создание новой команды."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    logger.info(f"Попытка создания команды пользователем {user.id} с именем {request.name}")
    
    try:
        command_service = CommandService(session)
        await command_service.create_command(user, request, event_name)
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно создана"}
        )
    except (BadRequestException, InternalServerErrorException) as e:
        # Перехватываем ожидаемые ошибки из сервиса
        status_code = 400 if isinstance(e, BadRequestException) else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при создании команды: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Не удалось создать команду.")

@router.post("/command/delete")
async def delete_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Удаление команды капитаном."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    logger.info(f"Попытка удаления команды пользователем {user.id}")
    
    try:
        command_service = CommandService(session)
        await command_service.delete_command(user)
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно удалена"}
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        # Логируем ID пользователя, т.к. ID команды может быть недоступен
        logger.error(f"Ошибка при удалении команды пользователя {user.id}: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Не удалось удалить команду.")

@router.post("/command/rename")
async def rename_command(
    request: CommandEdit,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Переименование команды капитаном."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    logger.info(f"Попытка изменения команды пользователем {user.id} на {request.name}")
    
    try:
        command_service = CommandService(session)
        await command_service.rename_command(user, request)
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно обновлена"}
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при переименовании команды пользователя {user.id}: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Не удалось переименовать команду.")

@router.post("/command/leave")
async def leave_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Выход пользователя из команды."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    logger.info(f"Попытка выхода из команды пользователем {user.id}")
    
    try:
        command_service = CommandService(session)
        await command_service.leave_command(user)
        return JSONResponse(
            status_code=200,
            content={"message": "Вы успешно покинули команду"}
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при выходе из команды пользователя {user.id}: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Не удалось выйти из команды.")

@router.post("/command/remove_user")
async def remove_user_from_command(
    user_id: int = Body(..., embed=True),
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Исключение пользователя из команды капитаном."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
        
    logger.info(f"Попытка исключения пользователя {user_id} из команды пользователем {user.id}")
    
    try:
        command_service = CommandService(session)
        await command_service.remove_user_from_command(user, user_id)
        return JSONResponse(
            status_code=200,
            content={"message": "Пользователь успешно исключен из команды"}
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при исключении пользователя {user_id} из команды капитаном {user.id}: {str(e)}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Не удалось исключить пользователя из команды.")

@router.post("/update_profile")
async def update_profile(
    request: UpdateProfileRequest,
    session: AsyncSession = Depends(get_session_without_commit), # Use without_commit
    user: User = Depends(get_current_user)
):
    """Обновление профиля пользователя."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    
    try:
        user_service = UserService(session)
        await user_service.update_profile(user, request)
        return {"ok": True, "message": "Профиль успешно обновлен"}
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Логирование уже происходит в сервисе или общем обработчике
        raise HTTPException(status_code=500, detail="Ошибка сервера при обновлении профиля.")

# Проверка активности события
@router.get("/event/status")
async def check_event_status(
    session: AsyncSession = Depends(get_session_without_commit), # Changed to without_commit
    user: Optional[User] = Depends(get_current_user),
    event_name: str = Depends(get_current_event_name)
):
    """Проверяет, активно ли текущее событие."""
    # TODO: Перенести логику в EventService - DONE
    try:
        event_service = EventService(session)
        is_active = await event_service.check_event_status(user, event_name)
        return {"is_active": is_active}
    except Exception as e:
        # Логика обработки ошибок уже внутри сервиса, но оставим общую защиту
        logger.error(f"Непредвиденная ошибка при вызове EventService.check_event_status: {e}", exc_info=True)
        # Возвращаем False как безопасное значение по умолчанию
        return {"is_active": False}

@router.get("/stats/registrations")
async def get_registration_stats(
    session: AsyncSession = Depends(get_session_without_commit), # Changed to without_commit
    user: User = Depends(get_current_user), # Require user for permission check
    event_name: str = Depends(get_current_event_name)
):
    """Получает статистику по зарегистрированным пользователям и командам."""
    # TODO: Перенести логику в StatsService - DONE
    
    # Проверяем авторизацию (базовая проверка)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    
    try:
        stats_service = StatsService(session)
        stats = await stats_service.get_registration_stats(user, event_name)
        return JSONResponse(content={"ok": True, "stats": stats})
        
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InternalServerErrorException as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении статистики регистраций: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при получении статистики")

@router.get("/users/looking_for_team")
async def get_users_looking_for_team(
    session: AsyncSession = Depends(get_session_without_commit), # Только чтение
    user: User = Depends(get_current_user)
):
    """Возвращает список пользователей, которые ищут команду."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    
    try:
        user_service = UserService(session)
        users_list = await user_service.get_users_looking_for_team(user.id)
        return {"ok": True, "users": users_list}
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей, ищущих команду: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при получении списка пользователей")

# Новые эндпоинты для работы с баллами пользователей
# TODO: Перенести логику в ProgramService

@router.post("/program/add_score")
async def add_score(
    user_id: int = Body(..., embed=True),
    score_data: ProgramScoreAdd = Body(...),
    session: AsyncSession = Depends(get_session_with_commit),
    current_user: User = Depends(get_current_user) # Renamed user to current_user for clarity
):
    """Добавляет баллы пользователю (только CTC/Организатор)."""
    # TODO: Перенести логику в ProgramService - DONE
    
    # Проверяем авторизацию
    if not current_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")

    try:
        program_service = ProgramService(session)
        total_score = await program_service.add_score(user_id, score_data, current_user)
        
        return {
            "ok": True,
            "message": f"Баллы успешно {'начислены' if score_data.score > 0 else 'списаны'}",
            "total_score": total_score
        }
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e)) # Ошибка уже залогирована в сервисе
    except Exception as e:
        # Общая непредвиденная ошибка
        logger.error(f"Непредвиденная ошибка в роутере /program/add_score: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при добавлении баллов")

@router.get("/program/user/{user_id}")
async def get_user_score(
    user_id: int,
    session: AsyncSession = Depends(get_session_without_commit), # Только чтение
    current_user: User = Depends(get_current_user) # Renamed user to current_user
):
    """Получает информацию о баллах пользователя."""
    # TODO: Перенести логику в ProgramService - DONE
    
    # Проверяем авторизацию
    if not current_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    try:
        program_service = ProgramService(session)
        score_data = await program_service.get_user_score(user_id, current_user)
        return {"ok": True, "data": score_data.model_dump()}
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    # except NotFoundException as e: # Сервис не выбрасывает NotFound для этого метода сейчас
    #     raise HTTPException(status_code=404, detail=str(e)) 
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e)) # Ошибка уже залогирована в сервисе
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в роутере /program/user/{user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при получении баллов")

@router.post("/program/qr_add_score")
async def qr_add_score(
    token: str = Body(..., embed=True),
    score_data: ProgramScoreAdd = Body(...),
    session: AsyncSession = Depends(get_session_with_commit),
    scanner_user: User = Depends(get_current_user)
):
    """Быстрое добавление баллов при сканировании QR-кода (только CTC/Организатор)."""
    # TODO: Перенести логику в ProgramService - DONE
    
    # Проверяем авторизацию сканирующего
    if not scanner_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    try:
        program_service = ProgramService(session)
        result_data = await program_service.qr_add_score(token, score_data, scanner_user)
        
        return {
            "ok": True,
            "message": f"Баллы успешно {'начислены' if score_data.score > 0 else 'списаны'}",
            **result_data # Добавляем user_id, user_name, total_score из сервиса
        }
    except ForbiddenException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except TokenExpiredException as e:
         logger.warning(f"Истекший токен при добавлении баллов по QR в роутере: {e}")
         raise HTTPException(status_code=401, detail=str(e))
    except InternalServerErrorException as e:
        raise HTTPException(status_code=500, detail=str(e)) # Ошибка уже залогирована в сервисе
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в роутере /program/qr_add_score: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при добавлении баллов по QR")

@router.get("/commands/leaderboard/{event_name}", response_model=CommandLeaderboardResponse)
async def get_command_leaderboard(
    event_name: str,
    session: AsyncSession = Depends(get_session_without_commit), # Только чтение
    user: Optional[User] = Depends(get_current_user) # Авторизация не обязательна
):
    """Возвращает лидерборд команд для события (расчет по формуле, доступен всем)."""
    # TODO: Перенести логику в CommandService или StatsService - DONE (StatsService)
    logger.info(f"Запрос лидерборда команд для события '{event_name}' (доступен всем)")

    try:
        stats_service = StatsService(session)
        leaderboard_data = await stats_service.get_command_leaderboard(event_name)
        
        # Проверяем, найден ли был лидерборд (сервис возвращает пустой объект, если событие не найдено)
        if not leaderboard_data.leaderboard and not await EventsDAO(session).get_event_id_by_name(event_name): # Дополнительная проверка, что событие не существует
            logger.warning(f"Событие с именем '{event_name}' не найдено для лидерборда")
            return CommandLeaderboardResponse(ok=False, message=f"Событие '{event_name}' не найдено")
        
        # Возвращаем успешный результат (может быть пустым, если команд нет)
        return CommandLeaderboardResponse(ok=True, data=leaderboard_data)

    except Exception as e:
        logger.error(f"Ошибка при получении лидерборда команд для события '{event_name}': {str(e)}", exc_info=True)
        # Сервис уже логирует ошибку и возвращает пустой лидерборд, 
        # но если произошла другая ошибка здесь, вернем 500
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             content=CommandLeaderboardResponse(ok=False, message="Внутренняя ошибка сервера при формировании лидерборда").model_dump()
        )

