from fastapi.templating import Jinja2Templates
from pathlib import Path

# Создаем экземпляр Jinja2Templates
templates = Jinja2Templates(directory=str(Path("app/templates")))

def get_templates() -> Jinja2Templates:
    """Функция для получения экземпляра шаблонизатора."""
    return templates 
