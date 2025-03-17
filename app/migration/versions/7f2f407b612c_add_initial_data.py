"""add_initial_data

Revision ID: 7f2f407b612c
Revises: 2c9f4dc0fbea
Create Date: 2025-03-17 03:15:20.389039

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.auth.models import RoleUserCommand, Role, Event
from app.config import EVENT_NAME

# revision identifiers, used by Alembic.
revision: str = '7f2f407b612c'
down_revision: Union[str, None] = '2c9f4dc0fbea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Получаем текущее время
    now = datetime.now()

    # Добавляем начальные данные
    op.bulk_insert(
        sa.table(
            'roles',
            sa.column('name', sa.String),
            sa.column('created_at', sa.TIMESTAMP),
            sa.column('updated_at', sa.TIMESTAMP),
        ),
        [
            {'name': 'guest', 'created_at': now, 'updated_at': now},
            {'name': 'organizer', 'created_at': now, 'updated_at': now},
            {'name': 'insider', 'created_at': now, 'updated_at': now},
        ]
    )

    op.bulk_insert(
        sa.table(
            'roleusercommands',
            sa.column('name', sa.String),
            sa.column('created_at', sa.TIMESTAMP),
            sa.column('updated_at', sa.TIMESTAMP),
        ),
        [
            {'name': 'member', 'created_at': now, 'updated_at': now},
            {'name': 'captain', 'created_at': now, 'updated_at': now},
        ]
    )

    op.bulk_insert(
        sa.table(
            'events',
            sa.column('name', sa.String),
            sa.column('created_at', sa.TIMESTAMP),
            sa.column('updated_at', sa.TIMESTAMP),
        ),
        [
            {'name': EVENT_NAME, 'created_at': now, 'updated_at': now},
        ]
    )


def downgrade() -> None:
    pass
