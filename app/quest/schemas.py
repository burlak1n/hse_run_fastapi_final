
from pydantic import BaseModel


class BlockFilter(BaseModel):
    language_id: int = 1

class FindQuestionsForBlock(BaseModel):
    block_id: int | None = None

class FindAnswersForQuestion(BaseModel):
    question_id: int | None = None
