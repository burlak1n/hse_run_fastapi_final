"""add_image_block

Revision ID: 133af3bb6219
Revises: 773c156d4d4d
Create Date: 2025-05-03 14:15:25.515045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '133af3bb6219'
down_revision: Union[str, None] = '773c156d4d4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('blocks', sa.Column('image_path', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('blocks', 'image_path')
    # ### end Alembic commands ###
