from app.dao.base import BaseDAO
from app.quest.models import Block

class BlocksDAO(BaseDAO):
    model = Block
