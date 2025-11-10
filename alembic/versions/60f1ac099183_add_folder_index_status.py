"""add_folder_index_status

Revision ID: 60f1ac099183
Revises: 3da82da71390
Create Date: 2025-11-10 04:02:55.880598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60f1ac099183'
down_revision: Union[str, None] = '3da82da71390'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаём таблицу folder_index_status для отслеживания состояния индексации папок
    op.create_table(
        'folder_index_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('folder_path', sa.Text(), nullable=False),
        sa.Column('root_hash', sa.Text(), nullable=True),
        sa.Column('last_indexed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'folder_path', name='uq_folder_status')
    )
    op.create_index('ix_folder_index_status_owner', 'folder_index_status', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_folder_index_status_owner', table_name='folder_index_status')
    op.drop_table('folder_index_status')
