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
    full_name: Optional[str] = None
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
