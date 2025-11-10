"""add_user_profile_fields

Revision ID: 7949e1970345
Revises: 5ffc684e6693
Create Date: 2025-11-10 03:17:51.213830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7949e1970345'
down_revision: Union[str, None] = '5ffc684e6693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('first_name', sa.String(length=128), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=128), nullable=True))
    op.add_column('users', sa.Column('last_folder', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_folder')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
