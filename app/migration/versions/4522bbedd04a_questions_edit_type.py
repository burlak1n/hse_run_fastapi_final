"""questions_edit_type

Revision ID: 4522bbedd04a
Revises: 4698eb6ebf5b
Create Date: 2025-03-24 23:47:00.186277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4522bbedd04a'
down_revision: Union[str, None] = '4698eb6ebf5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем временную таблицу, если она существует
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_questions")
    
    # Создаем новую таблицу с измененным типом столбца
    with op.batch_alter_table('questions') as batch_op:
        batch_op.alter_column('geo_answered', type_=sa.String)
        batch_op.alter_column('text_answered', type_=sa.String)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Возвращаем старый тип столбца
    with op.batch_alter_table('questions') as batch_op:
        batch_op.alter_column('geo_answered', type_=sa.Boolean)
        batch_op.alter_column('text_answered', type_=sa.BOOLEAN)
    # ### end Alembic commands ###
