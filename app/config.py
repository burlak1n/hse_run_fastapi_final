import os
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    DB_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/db.sqlite3"
    REDIS_URL: str = "redis://localhost:6379/0"  # Default Redis URL
    USE_REDIS: bool = (
        True  # Master switch for Redis features (enabled by default for sessions)
    )

    model_config = SettingsConfigDict(env_file=f"{BASE_DIR}/.env", extra="ignore")
    BASE_URL: str = "https://hserun.ru"
    SESSION_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # 1 неделя
    DEBUG: bool = False


class EventConfig:
    def __init__(
        self,
        address="Хитровский перeулок, 2/8, стр.5",
        date="27 апреля 2025",
        number="29",
        start_time="12:00",
        end_time="16:00",
        name="HSERUN29",
        description="HSE RUN - культурно-исторический квест по Москве",
        version="1.0.0",
    ):
        self.address = address
        self.date = date
        self.number = number
        self.start_time = start_time
        self.end_time = end_time
        self.name = name
        self.description = description
        self.version = version


event_config = EventConfig()

# Получаем параметры для загрузки переменных среды
settings = Settings()
database_url = settings.DB_URL
BASE_URL = settings.BASE_URL

CURRENT_EVENT_NAME = "HSERUN29"
CAPTAIN_ROLE_NAME = "captain"

# Конфигурация доменов для мультидоменной поддержки
DOMAIN_EVENT_MAPPING: Dict[str, str] = {
    "hserun.ru": "HSERUN29",
    "technoquestcroc.ru": "KRUN",  # Пример для будущего события
}

# Конфигурации событий
EVENT_CONFIGS: Dict[str, EventConfig] = {
    "HSERUN29": EventConfig(),
    "KRUN": EventConfig(
        address="Волочаевская ул., 5, корп. 1",
        date="15 июля 2025",
        number="1",
        start_time="17:00",
        end_time="20:30",
        name="TECHNO QUEST",
        description="Большой культурно-айтишный квест по Москве специально для кроковцев",
        version="1.0.0",
    ),
}


def get_event_config(event_name: str) -> EventConfig:
    """Возвращает конфигурацию события по имени"""
    return EVENT_CONFIGS.get(event_name, EVENT_CONFIGS["HSERUN29"])


def get_event_name_by_domain(domain: str) -> str:
    """Возвращает имя события по домену"""
    return DOMAIN_EVENT_MAPPING.get(domain, "HSERUN29")


DEBUG = False
