import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

# Добавляем корневую директорию проекта в sys.path
# Это нужно, чтобы можно было импортировать модули из backend.app
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.dao.database import async_session_maker
# Используем относительные импорты для моделей
from ..app.auth.models import Command, User, CommandsUser
from ..app.quest.models import Attempt, AttemptType


async def main():
    """
    Добавляет успешную попытку 'money_start' для каждой команды,
    у которой еще нет такой попытки.
    """
    # Убираем инициализацию, предполагая, что БД уже настроена миграциями
    # print("Инициализация базы данных...")
    # await init_db()
    # print("База данных инициализирована.")

    # Используем async_session_maker вместо async_session_factory
    async with async_session_maker() as session:
        print("Получение типа попытки 'money_start'...")
        # Используем name вместо slug
        money_start_type_result = await session.execute(
            select(AttemptType).where(AttemptType.name == 'money_start')
        )
        money_start_type = money_start_type_result.scalar_one_or_none()

        if not money_start_type:
            # Уточняем сообщение об ошибке
            print("Ошибка: Тип попытки с именем 'money_start' не найден.")
            return

        print(f"Тип попытки 'money_start' найден (ID: {money_start_type.id}).")

        print("Получение всех команд с их пользователями...")
        # Загружаем связанных пользователей сразу, чтобы избежать N+1 запросов
        result = await session.execute(
            select(Command).options(selectinload(Command.users).selectinload(CommandsUser.user))
        )
        commands = result.scalars().unique().all() # .unique() нужен из-за join'ов при selectinload
        print(f"Найдено {len(commands)} команд.")

        new_attempts = []
        skipped_commands = 0
        commands_without_users = 0
        for command in commands:
            # Получаем ID первого пользователя команды (или капитана, если логика будет уточнена)
            # ВАЖНО: Уточнить, какой пользователь должен быть связан с этой попыткой
            first_user_assoc = next((cu for cu in command.users), None)
            if not first_user_assoc:
                 print(f"Предупреждение: Команда {command.id} ('{command.name}') не имеет пользователей, попытка не будет создана.")
                 commands_without_users += 1
                 continue

            user_id_for_attempt = first_user_assoc.user_id

            # Проверяем, есть ли уже 'успешная' (is_true=True) попытка 'money_start' для этой команды
            # Важно: Проверяем для конкретного user_id, если это требуется.
            # Если попытка должна быть уникальной на команду, независимо от пользователя,
            # то user_id в where не нужен, но модель Attempt все равно требует user_id при создании.
            # Текущая проверка ищет попытку, связанную с первым пользователем.
            existing_attempt_result = await session.execute(
                select(Attempt).where(
                    Attempt.command_id == command.id,
                    Attempt.attempt_type_id == money_start_type.id,
                    Attempt.user_id == user_id_for_attempt, # Проверяем для этого пользователя
                    Attempt.is_true == True # Используем is_true вместо status
                )
            )
            if existing_attempt_result.scalar_one_or_none():
                # print(f"Команда {command.id}: Успешная попытка 'money_start' уже существует для пользователя {user_id_for_attempt}, пропускаем.")
                skipped_commands += 1
                continue

            # print(f"Команда {command.id}: Добавление попытки 'money_start' для пользователя {user_id_for_attempt}.")
            new_attempt = Attempt(
                command_id=command.id,
                user_id=user_id_for_attempt, # Используем ID первого пользователя
                attempt_type_id=money_start_type.id,
                is_true=True, # Используем is_true вместо status
                # Убираем started_at и score, их нет в модели
                # started_at=datetime.now(timezone.utc),
                # score=0
                # Поле attempt_text является Optional[str], оставляем его пустым (None)
            )
            new_attempts.append(new_attempt)

        if new_attempts:
            print(f"Добавление {len(new_attempts)} новых попыток 'money_start'...")
            session.add_all(new_attempts)
            await session.commit()
            print("Новые попытки успешно добавлены.")
        else:
            print("Нет команд для добавления попыток 'money_start'.")

        if commands_without_users > 0:
            print(f"Предупреждение: {commands_without_users} команд пропущено из-за отсутствия пользователей.")

        if skipped_commands > 0:
             print(f"Пропущено {skipped_commands} команд (или пар команда-пользователь), так как у них уже есть успешная попытка 'money_start'.")

    print("Скрипт завершен.")


if __name__ == "__main__":
    # Убедимся, что скрипт запускается из корневой директории проекта
    # или из директории backend
    current_path = Path.cwd()
    if current_path != project_root and current_path != project_root / 'backend':
        print(f"Ошибка: Пожалуйста, запустите скрипт из корневой директории проекта ({project_root}) или из директории 'backend'.")
        sys.exit(1)

    # Если запускаем из корня, добавляем 'backend' к sys.path
    if current_path == project_root:
         sys.path.insert(0, str(project_root / 'backend'))
         # И меняем CWD на backend для корректной работы настроек (например, .env)
         import os
         os.chdir(project_root / 'backend')
         print(f"Изменена рабочая директория на: {os.getcwd()}")


    asyncio.run(main()) 