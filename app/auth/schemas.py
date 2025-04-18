from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional


class UserTelegramID(BaseModel):
    telegram_id: int = Field(description="Идентификатор пользователя в Telegram")

class TelegramModel(UserTelegramID):
    telegram_username: Optional[str] = Field(default=None, description="Имя пользователя в Telegram")

class UserFullname(BaseModel):
    full_name: str = Field(description="ФИО пользователя")

class UserFindCompleteRegistration(BaseModel):
    id: int = Field(description="ID пользователя в БД")

class UserMakeCompleteRegistration(UserFullname):
    role_id: int = Field(description="ID роли пользователя")

class UserBase(TelegramModel, UserFullname, UserTelegramID):
    pass

class SUserRegister(UserBase):
    pass

class SUserAddDB(UserBase):
    pass

class SUserAuth(TelegramModel):
    pass

class RoleModel(BaseModel):
    id: int = Field(description="Идентификатор роли")
    name: str = Field(description="Название роли")
    model_config = ConfigDict(from_attributes=True)

class ParticipantInfo(BaseModel):
    id: int
    full_name: str
    role: str

class CommandInfo(BaseModel):
    id: int
    name: str
    role: str
    event_id: int
    language_id: int
    participants: list[ParticipantInfo]

class InsiderInfoBase(BaseModel):
    student_organization: Optional[str] = Field(default=None, description="Студенческая организация инсайдера")
    geo_link: Optional[str] = Field(default=None, description="Ссылка на геолокацию 2ГИС")

class InsiderInfoCreate(InsiderInfoBase):
    user_id: int = Field(description="ID пользователя-инсайдера")

class InsiderInfoUpdate(InsiderInfoBase):
    pass

class InsiderInfoResponse(InsiderInfoBase):
    id: int
    user_id: int
    
    model_config = ConfigDict(from_attributes=True)

class CompleteRegistrationRequest(BaseModel):
    full_name: str
    student_organization: Optional[str] = None
    geo_link: Optional[str] = None

class UpdateProfileRequest(BaseModel):
    full_name: str
    student_organization: Optional[str] = None
    geo_link: Optional[str] = None

class SUserInfo(UserBase):
    id: int = Field(description="Идентификатор пользователя")
    role: Optional[RoleModel] = Field(
        default=None,
        description="Роль пользователя"
    )
    commands: list[CommandInfo] = Field(
        default_factory=list,
        description="Список команд пользователя"
    )
    is_looking_for_friends: bool = Field(
        default=False,
        description="Флаг поиска команды"
    )
    insider_info: Optional[InsiderInfoBase] = Field(
        default=None,
        description="Информация инсайдера (если пользователь является инсайдером)"
    )

    model_config = ConfigDict(from_attributes=True)

class CommandName(BaseModel):
    name: str

class CommandEdit(CommandName):
    language_id: int

class CommandBase(CommandEdit):
    event_id: int

class EventID(BaseModel):
    name: str

class CommandID(BaseModel):
    id: int

class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str
    registration_code: Optional[str] = None
    
class SessionGet(BaseModel):
    token: str

class SessionFindUpdate(BaseModel):
    user_id: int
    is_active: bool

class SessionMakeUpdate(BaseModel):
    is_active: bool
    expires_at: datetime

class SessionCreate(BaseModel):
    user_id: int
    token: str
    expires_at: datetime
    is_active: bool

class CommandsUserBase(BaseModel):
    command_id: int = Field(description="ID команды")
    user_id: int = Field(description="ID пользователя")
    role_id: int = Field(description="ID роли пользователя в команде")

class CommandsUserCreate(CommandsUserBase):
    pass

class CommandsUser(CommandsUserBase):
    id: int = Field(description="ID записи")
    
    model_config = ConfigDict(from_attributes=True)

class RoleFilter(BaseModel):
    name: str