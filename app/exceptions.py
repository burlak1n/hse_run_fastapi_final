from fastapi import status, HTTPException

class NotFoundException(Exception):
    def __init__(self, detail='Не найдено'):
        self.detail = detail
        super().__init__(detail)

class BadRequestException(Exception):
    def __init__(self, detail='Некорректный запрос'):
        self.detail = detail
        super().__init__(detail)

# Пользователь уже существует
class UserAlreadyExistsException(Exception):
    def __init__(self, detail='Пользователь уже существует'):
        self.detail = detail
        super().__init__(detail)

# Пользователь не найден
class UserNotFoundException(Exception):
    def __init__(self, detail='Пользователь не найден'):
        self.detail = detail
        super().__init__(detail)

# Отсутствует идентификатор пользователя
class UserIdNotFoundException(Exception):
    def __init__(self, detail='Отсутствует идентификатор пользователя'):
        self.detail = detail
        super().__init__(detail)

# Неверный идентификатор или пароль
class IncorrectTelegramIdOrPasswordException(Exception):
    def __init__(self, detail='Неверный идентификатор или пароль'):
        self.detail = detail
        super().__init__(detail)

# Токен истек
class TokenExpiredException(Exception):
    def __init__(self, detail='Токен истек'):
        self.detail = detail
        super().__init__(detail)

# Некорректный формат токена
class InvalidTokenFormatException(Exception):
    def __init__(self, detail='Некорректный формат токена'):
        self.detail = detail
        super().__init__(detail)

# Токен отсутствует в заголовке
class TokenNoFound(Exception):
    def __init__(self, detail='Токен не найден'):
        self.detail = detail
        super().__init__(detail)

# Невалидный JWT токен
class NoJwtException(Exception):
    def __init__(self, detail='Токен не валидный'):
        self.detail = detail
        super().__init__(detail)

# Не найден ID пользователя
class NoUserIdException(Exception):
    def __init__(self, detail='Не найден ID пользователя'):
        self.detail = detail
        super().__init__(detail)

# Недостаточно прав
class ForbiddenException(Exception):
    def __init__(self, detail='Недостаточно прав'):
        self.detail = detail
        super().__init__(detail)

class TokenInvalidFormatException(Exception):
    def __init__(self, detail="Неверный формат токена. Ожидается 'Bearer <токен>'"):
        self.detail = detail
        super().__init__(detail)

# Событие не найдено
class EventNotFoundException(Exception):
    def __init__(self, detail='Событие не найдено'):
        self.detail = detail
        super().__init__(detail)

# Внутренняя ошибка сервера
class InternalServerErrorException(Exception):
    def __init__(self, detail='Внутренняя ошибка сервера'):
        self.detail = detail
        super().__init__(detail)

# --- Quest Specific Exceptions ---

# Пользователь не состоит в команде
class UserNotInCommandException(Exception):
    def __init__(self, detail='Пользователь не состоит ни в одной команде'):
        self.detail = detail
        super().__init__(detail)

# Блок не найден
class BlockNotFoundException(Exception):
    def __init__(self, detail='Блок квеста не найден'):
        self.detail = detail
        super().__init__(detail)

# Загадка не найдена
class RiddleNotFoundException(Exception):
    def __init__(self, detail='Загадка не найдена'):
        self.detail = detail
        super().__init__(detail)

# Несоответствие языка блока и команды
class LanguageMismatchException(Exception):
    def __init__(self, detail='Язык блока не совпадает с языком команды'):
        self.detail = detail
        super().__init__(detail)

# Награда за загадку уже выдана
class RewardAlreadyGivenException(Exception):
    def __init__(self, detail='Награда за эту загадку уже была выдана команде'):
        self.detail = detail
        super().__init__(detail)

# Тип попытки не найден (ошибка конфигурации)
class AttemptTypeNotFoundException(Exception):
    def __init__(self, detail='Тип попытки не найден в базе данных'):
        self.detail = detail
        super().__init__(detail)

# Подсказка недоступна для этой загадки
class HintUnavailableException(Exception):
    def __init__(self, detail='Подсказка недоступна для этой загадки'):
        self.detail = detail
        super().__init__(detail)

# Недостаточно монет
class InsufficientCoinsException(Exception):
    def __init__(self, detail='Недостаточно монет для выполнения операции'):
        self.detail = detail
        super().__init__(detail)

# Вопрос не назначен инсайдеру
class QuestionNotAssignedException(Exception):
    def __init__(self, detail='Этот вопрос не назначен вам'):
        self.detail = detail
        super().__init__(detail)

# Посещение уже отмечено
class AttendanceAlreadyMarkedException(Exception):
    def __init__(self, detail='Посещение этого места для данной команды уже было отмечено'):
        self.detail = detail
        super().__init__(detail)

# Нельзя отметить посещение нерешенной загадки
class CannotMarkUnsolvedException(Exception):
    def __init__(self, detail='Невозможно отметить посещение: команда еще не решила эту загадку'):
        self.detail = detail
        super().__init__(detail)
