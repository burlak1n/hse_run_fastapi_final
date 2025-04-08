from pydantic import BaseModel, Field
from typing import List, Optional


class BlockFilter(BaseModel):
    id: Optional[int] = None
    language_id: Optional[int] = None

class FindQuestionsForBlock(BaseModel):
    block_id: int

class FindAnswersForQuestion(BaseModel):
    question_id: int

class FindInsidersForQuestion(BaseModel):
    question_id: int
