from sqladmin import Admin
from app.dao.database import engine
from app.cms.views import UserAdmin, RoleAdmin, CommandAdmin

def init_admin(app, base_url: str = "/admin"):
    """Инициализация SQLAdmin"""
    admin = Admin(app, engine, base_url=base_url)
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(CommandAdmin)
