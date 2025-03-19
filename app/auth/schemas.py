from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional


class UserTelegramID(BaseModel):
    telegram_id: int = Field(description="Идентификатор пользователя в Telegram")

class TelegramModel(UserTelegramID):
    telegram_username: str = Field(description="Имя пользователя в Telegram")

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


class SUserInfo(UserBase):
    id: int = Field(description="Идентификатор пользователя")
    role_id: Optional[int] = Field(
        default=None,
        description="Идентификатор роли пользователя. Если NULL - пользователь неактивен"
    )
    role: Optional[RoleModel] = Field(
        default=None,
        exclude=True,
        description="Роль пользователя"
    )

    @computed_field
    def role_name(self) -> Optional[str]:
        return self.role.name if self.role else None

    model_config = ConfigDict(from_attributes=True)

class CommandName(BaseModel):
    name: str

class CommandBase(CommandName):
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