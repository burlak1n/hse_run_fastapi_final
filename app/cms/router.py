from sqladmin import Admin
from app.dao.database import engine
from app.cms import views

def init_admin(app, base_url: str = "/admin"):
    """Инициализация SQLAdmin"""
    admin = Admin(app, engine, base_url=base_url)
    
    # Автоматически регистрируем все классы ModelView из views
    for name, view in vars(views).items():
        if name.endswith('Admin') and hasattr(view, 'model'):
            admin.add_view(view)
