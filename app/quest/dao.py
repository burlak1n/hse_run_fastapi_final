from app.dao.base import BaseDAO
from app.quest.models import Block, Language

class BlocksDAO(BaseDAO):
    model = Block

class LanguagesDAO(BaseDAO):
    model = Language
    