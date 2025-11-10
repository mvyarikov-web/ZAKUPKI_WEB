"""add_user_documents_table

Revision ID: 3da82da71390
Revises: 7a22d26c725f
Create Date: 2025-11-10 03:56:57.826884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3da82da71390'
down_revision: Union[str, None] = '7a22d26c725f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаём таблицу user_documents для связи пользователей и документов
    op.create_table(
        'user_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('access_level', sa.String(50), nullable=False, server_default='read'),
        sa.Column('is_soft_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'document_id', name='uq_user_document')
    )
    
    # Индексы для быстрого поиска
    op.create_index('ix_user_documents_user_id', 'user_documents', ['user_id'])
    op.create_index('ix_user_documents_document_id', 'user_documents', ['document_id'])


def downgrade() -> None:
    op.drop_index('ix_user_documents_document_id', table_name='user_documents')
    op.drop_index('ix_user_documents_user_id', table_name='user_documents')
    op.drop_table('user_documents')
