from pydantic import BaseModel, ConfigDict, Field, computed_field


class UserID(BaseModel):
    telegram_id: int = Field(description="Идентификатор пользователя в Telegram")

class TelegramModel(UserID):
    telegram_username: str = Field(description="Имя пользователя в Telegram")

class UserFullname(BaseModel):
    full_name: str = Field(description="Имя и фамилия пользователя")

class UserBase(TelegramModel, UserFullname, UserID):
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
    role: RoleModel = Field(exclude=True)

    @computed_field
    def role_name(self) -> str:
        return self.role.name

    @computed_field
    def role_id(self) -> int:
        return self.role.id
