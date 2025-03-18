from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.responses import FileResponse

directory = "app/static/html"

templates = Jinja2Templates(directory=directory)

def render_template(request: Request, template_name: str, context: dict=None):
    if context is None:
        return FileResponse(f"{directory}/{template_name}")
    return templates.TemplateResponse(template_name, {"request": request, **context})
