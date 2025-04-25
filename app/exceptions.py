from fastapi import status, HTTPException

# Пользователь уже существует
UserAlreadyExistsException = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail='Пользователь уже существует'
)

# Пользователь не найден
UserNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Пользователь не найден'
)

# Отсутствует идентификатор пользователя
UserIdNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Отсутствует идентификатор пользователя'
)

# Неверный идентификатор или пароль
IncorrectTelegramIdOrPasswordException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Неверный идентификатор или пароль'
)

# Токен истек
TokenExpiredException = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Токен истек'
)

# Некорректный формат токена
InvalidTokenFormatException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Некорректный формат токена'
)


# Токен отсутствует в заголовке
TokenNoFound = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Токен не найден'
)

# Невалидный JWT токен
NoJwtException = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Токен не валидный'
)

# Не найден ID пользователя
NoUserIdException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Не найден ID пользователя'
)

# Недостаточно прав
ForbiddenException = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail='Недостаточно прав'
)

TokenInvalidFormatException = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат токена. Ожидается 'Bearer <токен>'"
)

# Событие не найдено
EventNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Событие не найдено'
)

# Внутренняя ошибка сервера
InternalServerErrorException = HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail='Внутренняя ошибка сервера'
)

# --- Quest Specific Exceptions ---

# Пользователь не состоит в команде
UserNotInCommandException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Пользователь не состоит ни в одной команде'
)

# Блок не найден
BlockNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Блок квеста не найден'
)

# Загадка не найдена
RiddleNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Загадка не найдена'
)

# Несоответствие языка блока и команды
LanguageMismatchException = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail='Язык блока не совпадает с языком команды'
)

# Награда за загадку уже выдана
RewardAlreadyGivenException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Награда за эту загадку уже была выдана команде'
)

# Тип попытки не найден (ошибка конфигурации)
AttemptTypeNotFoundException = HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail='Тип попытки не найден в базе данных'
)

# Подсказка недоступна для этой загадки
HintUnavailableException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail='Подсказка недоступна для этой загадки'
)

# Недостаточно монет
InsufficientCoinsException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Недостаточно монет для выполнения операции'
)

# Вопрос не назначен инсайдеру
QuestionNotAssignedException = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail='Этот вопрос не назначен вам'
)

# Посещение уже отмечено
AttendanceAlreadyMarkedException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Посещение этого места для данной команды уже было отмечено'
)

# Нельзя отметить посещение нерешенной загадки
CannotMarkUnsolvedException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail='Невозможно отметить посещение: команда еще не решила эту загадку'
)
