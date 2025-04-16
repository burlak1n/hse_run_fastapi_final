"""make_telegram_username_nullable_batch

Revision ID: 6aa9bf81fc2b
Revises: 6d3cb10d5d11
Create Date: 2025-04-17 00:47:05.748522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6aa9bf81fc2b'
down_revision: Union[str, None] = '6d3cb10d5d11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite не поддерживает изменение столбцов с помощью ALTER напрямую,
    # поэтому используем batch_alter_table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('telegram_username',
                              existing_type=sa.VARCHAR(),
                              nullable=True)


def downgrade() -> None:
    # Отмена изменений
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('telegram_username',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
