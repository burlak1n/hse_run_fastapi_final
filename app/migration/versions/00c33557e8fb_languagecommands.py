"""LanguageCommands

Revision ID: 00c33557e8fb
Revises: 05b3acda7aff
Create Date: 2025-03-21 08:23:11.629474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00c33557e8fb'
down_revision: Union[str, None] = '05b3acda7aff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('commands') as batch_op:
        batch_op.add_column(sa.Column('language_id', sa.Integer(), nullable=False))
        batch_op.create_foreign_key(
            'fk_commands_language_id_languages',
            'languages', ['language_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('commands') as batch_op:
        batch_op.drop_constraint('fk_commands_language_id_languages', type_='foreignkey')
        batch_op.drop_column('language_id')
