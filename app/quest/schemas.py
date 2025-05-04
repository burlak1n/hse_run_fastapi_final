from pydantic import BaseModel, Field
from typing import List, Optional, Union


class BlockFilter(BaseModel):
    id: Optional[int] = None
    language_id: Optional[int] = None

class FindQuestionsForBlock(BaseModel):
    block_id: int

class FindAnswersForQuestion(BaseModel):
    question_id: int

class FindInsidersForQuestion(BaseModel):
    question_id: int

class MarkInsiderAttendanceRequest(BaseModel):
    question_id: int
    command_id: int
    scanned_user_id: int

class AnswerRequest(BaseModel):
    """Schema for checking an answer."""
    answer: str = Field(..., description="The user's answer text")

# --- Response Schemas ---

# Base Riddle Schema (common fields)
class RiddleBase(BaseModel):
    id: int
    title: Optional[str] = None # Optional for unsolved riddles

# Riddle Schema for lists (brief version)
class RiddleBrief(RiddleBase):
    image_path: Optional[str] = None
    has_hint: bool
    hint: Optional[str] = None

# Riddle Schema for detailed view (full version, shown when solved)
class RiddleDetail(RiddleBase):
    text_answered: Optional[str] = None
    image_path_answered: Optional[str] = None
    geo_answered: Optional[str] = None
    insiderLinks: Optional[List[str]] = None
    has_insider_attempt: bool
    has_hint: bool
    hint: Optional[str] = None

# Union type for riddle responses
RiddleResponseData = Union[RiddleDetail, RiddleBrief]

# Block Schema used within GetAllBlocksResponse
class BlockResponse(BaseModel):
    id: int
    title: str
    language_id: int
    # Include either riddles list OR counts/progress
    riddles: Optional[List[RiddleResponseData]] = None
    solved_count: Optional[int] = None
    total_count: Optional[int] = None
    insider_count: Optional[int] = None
    progress: Optional[int] = None
    error: Optional[str] = None # In case of session issues in utils

# Main response schema for GET / endpoint
class GetAllBlocksResponse(BaseModel):
    ok: bool
    message: str
    team_score: int
    team_coins: int
    blocks: List[BlockResponse]

# Response schema for GET /{block_id} endpoint
class GetBlockResponse(BaseModel):
    ok: bool
    message: str
    team_score: int
    team_coins: int
    block: BlockResponse # Single block, expecting riddles to be populated

# Response schema for POST /check-answer/{riddle_id} endpoint
class CheckAnswerResponse(BaseModel):
    ok: bool
    isCorrect: bool
    # updatedRiddle can be RiddleDetail/RiddleBrief if correct, or null if incorrect
    updatedRiddle: Optional[RiddleResponseData] = None 
    team_score: int
    team_coins: int

# Response schema for GET /hint/{riddle_id} endpoint
class HintResponse(BaseModel):
    ok: bool
    hint: str # The hint text (or path)
    team_score: int
    team_coins: int

# Schema for insider information
class InsiderInfo(BaseModel):
    id: int
    full_name: str
    telegram_username: Optional[str] = None

# Response schema for GET /riddle/{riddle_id}/insiders endpoint
class RiddleInsidersResponse(BaseModel):
    ok: bool
    riddle_id: int
    riddle_title: str
    insiders: List[InsiderInfo]

# Response schema for POST /mark-insider-attendance endpoint
class MarkAttendanceResponse(BaseModel):
    ok: bool
    message: str

# Schema for individual task status for insiders
class InsiderTaskStatus(BaseModel):
    id: int
    title: str
    is_attendance_marked: bool
    can_mark_attendance: bool

# Response schema for GET /insider-tasks-status endpoint
class GetInsiderTasksResponse(BaseModel):
    ok: bool
    tasks: List[InsiderTaskStatus]

# Schema for participant info within command stats
class ParticipantInfo(BaseModel):
    id: int
    name: Optional[str] = None
    role: str

# Schema for individual command statistics
class CommandStats(BaseModel):
    id: int
    name: str
    language: str
    score: int
    coins: int
    solved_riddles_count: int
    participants_count: int
    participants: List[ParticipantInfo]

# Response schema for GET /stats/commands endpoint
class GetCommandsStatsResponse(BaseModel):
    ok: bool
    stats: List[CommandStats]

class AnswerInfo(BaseModel):
    id: int
    answer_text: str

class QuestionStructureInfo(BaseModel):
    id: int
    title: str
    image_path: Optional[str] = None
    hint_path: Optional[str] = None
    text_answered: Optional[str] = None
    image_path_answered: Optional[str] = None
    solved_percent: float = 0.0

class BlockStructureInfo(BaseModel):
    id: int
    title: str
    language_id: int
    questions: List[QuestionStructureInfo] = []

class EventQuestStructureResponse(BaseModel):
    ok: bool = True
    event_name: str
    blocks: List[BlockStructureInfo] = []

# --- Новые схемы для /blocks/simple --- 
class SimpleQuestionInfo(BaseModel):
    id: int
    title: str
    image_path: Optional[str] = None
    hint_path: Optional[str] = None # Добавим подсказку для справки

class SimpleBlockInfo(BaseModel):
    id: int
    title: str
    language_id: int
    questions: List[SimpleQuestionInfo]

class GetAllSimpleBlocksResponse(BaseModel):
    ok: bool = True
    blocks: List[SimpleBlockInfo]
# --- Конец новых схем --- 

class QuestionFilter(BaseModel):
    block_id: Optional[int] = None

class AnswerFilter(BaseModel):
    question_id: Optional[int] = None

class FindAnswersForQuestion(AnswerFilter):
    question_id: int 

class FindQuestionsForBlock(QuestionFilter):
    block_id: int

class CheckAnswerResponse(BaseModel):
    isCorrect: bool
    updatedRiddle: Optional[RiddleResponseData] = None # Исправлено: RiddleInfo -> RiddleResponseData
    team_score: int
    team_coins: int

class HintResponse(BaseModel):
    hint: Optional[str]
    team_score: int
    team_coins: int

# --- Схемы для инсайдеров --- 
class QuestionInsiderFilter(BaseModel):
    question_id: Optional[int] = None
    user_id: Optional[int] = None

class FindInsidersForQuestion(QuestionInsiderFilter):
    question_id: int

class MarkInsiderAttendanceRequest(BaseModel):
    scanned_user_id: int # ID пользователя, чей QR-код сканируют
    command_id: int      # ID команды этого пользователя
    question_id: int     # ID вопроса (локации), где происходит сканирование

class MarkAttendanceResponse(BaseModel):
    pass # Просто OK или ошибка

class InsiderTaskStatus(BaseModel):
    id: int # question_id
    title: str
    is_attendance_marked: bool
    can_mark_attendance: bool

class GetInsiderTasksResponse(BaseModel):
    tasks: List[InsiderTaskStatus]

# --- Схемы для статистики команд (организатор) ---
class ParticipantInfo(BaseModel):
    id: int
    name: str
    role: str

class CommandStats(BaseModel):
    id: int
    name: str
    language: str
    score: int
    coins: int
    solved_riddles_count: int
    participants_count: int
    participants: List[ParticipantInfo]

class GetCommandsStatsResponse(BaseModel):
    stats: List[CommandStats]

# --- Схемы для структуры квеста (организатор) ---
class QuestionStructureInfo(BaseModel):
    id: int
    title: str
    image_path: Optional[str]
    hint_path: Optional[str]
    longread: Optional[str]
    image_path_answered: Optional[str] # Картинка после решения (если есть)
    solved_percent: float = 0.0

class BlockStructureInfo(BaseModel):
    id: int
    title: str
    image_path: Optional[str]
    language_id: int
    questions: List[QuestionStructureInfo]

class EventQuestStructureResponse(BaseModel):
    event_name: str
    blocks: List[BlockStructureInfo]
