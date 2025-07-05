import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from datetime import timedelta

class Settings(BaseSettings):
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    DB_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/db.sqlite3"
    REDIS_URL: str = "redis://localhost:6379/0" # Default Redis URL
    USE_REDIS: bool = True # Master switch for Redis features (enabled by default for sessions)

    model_config = SettingsConfigDict(env_file=f"{BASE_DIR}/.env")
    BASE_URL: str = "https://hserun.ru"
    SESSION_EXPIRE_SECONDS: int = 60*60*24*7 # 1 неделя
    DEBUG: bool = False

class EventConfig:
    address = "Хитровский перeулок, 2/8, стр.5"
    date = "27 апреля 2025"
    number = "29"
    start_time = "12:00"
    end_time = "16:00"
    name = "HSERUN29"
    description = "HSE RUN - культурно-исторический квест по Москве"
    version = "1.0.0"
    
event_config = EventConfig()

# Получаем параметры для загрузки переменных среды
settings = Settings()
database_url = settings.DB_URL
BASE_URL = settings.BASE_URL

CURRENT_EVENT_NAME = "HSERUN29"
CAPTAIN_ROLE_NAME = "captain"

DEBUG = False
