
from pydantic import BaseModel


class BlockFilter(BaseModel):
    language_id: int = 1