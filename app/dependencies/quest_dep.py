from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple

from app.auth.models import User, Command
from app.auth.dao import UsersDAO
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit
from app.exceptions import UserNotInCommandException # Import the specific exception

async def get_authenticated_user_and_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user) # Ensures user is authenticated
) -> Tuple[User, Command]:
    """
    Dependency to get the authenticated user and their associated command.
    Raises UserNotInCommandException if the user is not in a command.
    """
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user.id)
    if not command:
        raise UserNotInCommandException
    return user, command 