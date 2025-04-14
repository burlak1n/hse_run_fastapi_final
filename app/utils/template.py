from fastapi import Request
from fastapi.responses import HTMLResponse
from app.dependencies.template_dep import get_templates
from pathlib import Path
import os
import urllib.parse
from app.config import BASE_URL

# Получаем домен из BASE_URL для политики CSP
parsed_url = urllib.parse.urlparse(BASE_URL)
base_domain = parsed_url.netloc
base_scheme = parsed_url.scheme
base_domain_csp = f"{base_scheme}://{base_domain}"

STATIC_HTML_DIR = Path("app/static/html")

def render_template(template_name: str, request: Request = None, **context):
    """
    Рендерит HTML шаблон.
    
    Два режима работы:
    1. Если шаблон имеет расширение .html и находится в директории static/html, возвращает его напрямую
    2. Иначе, использует Jinja2 для рендеринга шаблона из директории templates
    
    Args:
        template_name: Имя шаблона (с расширением)
        request: Объект запроса FastAPI (для Jinja2)
        **context: Дополнительный контекст для шаблона
    
    Returns:
        HTMLResponse с отрендеренным шаблоном
    """
    if template_name.endswith('.html') and (STATIC_HTML_DIR / template_name).exists():
        # Режим статического HTML файла
        file_path = STATIC_HTML_DIR / template_name
        if not file_path.exists():
            raise FileNotFoundError(f"Шаблон {template_name} не найден")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return HTMLResponse(content=content)
    else:
        # Режим Jinja2
        templates = get_templates()
        return templates.TemplateResponse(template_name, {'request': request, **context})
