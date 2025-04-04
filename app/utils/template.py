from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
import os
import urllib.parse
from app.config import BASE_URL

# Получаем домен из BASE_URL для политики CSP
parsed_url = urllib.parse.urlparse(BASE_URL)
base_domain = parsed_url.netloc
base_scheme = parsed_url.scheme
base_domain_csp = f"{base_scheme}://{base_domain}"

# Создаем окружение шаблонизатора
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "html")
env = Environment(loader=FileSystemLoader(templates_dir))

def render_template(request: Request, template_name: str, context: dict = None) -> HTMLResponse:
    """
    Рендерит HTML шаблон, добавляя заголовки безопасности.
    
    Args:
        request: Объект запроса FastAPI
        template_name: Имя шаблона
        context: Контекст для шаблона
        
    Returns:
        HTMLResponse с отрендеренным шаблоном
    """
    if context is None:
        context = {}
    
    # Добавляем request в контекст для доступа к запросу внутри шаблона
    context["request"] = request
    
    # Получаем шаблон и рендерим его
    template = env.get_template(template_name)
    content = template.render(**context)
    
    # Создаем ответ с заголовками безопасности
    response = HTMLResponse(content=content)
    
    # Добавляем заголовки безопасности
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self' {base_domain_csp}; "
        f"script-src 'self' 'unsafe-inline' {base_domain_csp}; "
        f"style-src 'self' 'unsafe-inline' {base_domain_csp}; "
        f"img-src 'self' data: {base_domain_csp}; "
        f"connect-src 'self' {base_domain_csp}; "
        "frame-ancestors 'self'; "
        "form-action 'self'"
    )
    
    return response
