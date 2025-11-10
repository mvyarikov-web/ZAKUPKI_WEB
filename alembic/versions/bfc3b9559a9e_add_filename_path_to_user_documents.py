"""add_filename_path_to_user_documents

Revision ID: bfc3b9559a9e
Revises: 2458104a822b
Create Date: 2025-11-10 04:33:35.237800

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfc3b9559a9e'
down_revision: Union[str, None] = '2458104a822b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля для хранения имени файла и пути пользователя
    op.add_column('user_documents', sa.Column('original_filename', sa.Text(), nullable=True))
    op.add_column('user_documents', sa.Column('user_path', sa.Text(), nullable=True))
    op.add_column('user_documents', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
    
    # Индекс для поиска по пути
    op.create_index('idx_user_documents_path', 'user_documents', ['user_path'])


def downgrade() -> None:
    op.drop_index('idx_user_documents_path', table_name='user_documents')
    op.drop_column('user_documents', 'updated_at')
    op.drop_column('user_documents', 'user_path')
    op.drop_column('user_documents', 'original_filename')
