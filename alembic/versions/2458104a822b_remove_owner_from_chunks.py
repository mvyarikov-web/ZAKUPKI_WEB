"""remove_owner_from_chunks

Revision ID: 2458104a822b
Revises: 8914be589ae4
Create Date: 2025-11-10 04:29:20.599766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2458104a822b'
down_revision: Union[str, None] = '8914be589ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем owner_id из chunks (чанки принадлежат глобальным документам, не пользователям)
    op.drop_constraint('chunks_owner_id_fkey', 'chunks', type_='foreignkey')
    op.drop_index('idx_chunks_owner', table_name='chunks')
    op.drop_column('chunks', 'owner_id')


def downgrade() -> None:
    # Восстанавливаем owner_id (для отката)
    op.add_column('chunks', sa.Column('owner_id', sa.Integer(), nullable=False, server_default='1'))
    op.create_foreign_key('chunks_owner_id_fkey', 'chunks', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_chunks_owner', 'chunks', ['owner_id'])
