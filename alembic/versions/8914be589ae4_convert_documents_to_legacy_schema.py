"""convert_documents_to_legacy_schema

Revision ID: 8914be589ae4
Revises: 60f1ac099183
Create Date: 2025-11-10 04:27:19.584178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8914be589ae4'
down_revision: Union[str, None] = '60f1ac099183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Преобразуем documents к легаси-схеме (глобальное хранилище без привязки к пользователям)
    
    # 1. Удаляем индексы и связи с новой схемой
    op.drop_index('idx_documents_owner_status', table_name='documents')
    op.drop_constraint('documents_owner_id_fkey', 'documents', type_='foreignkey')
    
    # 2. Удаляем ненужные колонки новой схемы
    op.drop_column('documents', 'owner_id')
    op.drop_column('documents', 'original_filename')
    op.drop_column('documents', 'blob')
    op.drop_column('documents', 'storage_url')
    op.drop_column('documents', 'status')
    op.drop_column('documents', 'uploaded_at')
    op.drop_column('documents', 'indexed_at')
    
    # 3. Переименовываем content_type → mime
    op.alter_column('documents', 'content_type', new_column_name='mime', existing_type=sa.String(127))
    
    # 4. Добавляем легаси-поля для расчёта ценности
    op.add_column('documents', sa.Column('parse_status', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('access_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('documents', sa.Column('indexing_cost_seconds', sa.Float(), server_default='0', nullable=False))
    op.add_column('documents', sa.Column('last_accessed_at', sa.DateTime(), nullable=True))
    op.add_column('documents', sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
    
    # 5. Делаем sha256 уникальным (для глобальной дедупликации)
    op.create_unique_constraint('uq_documents_sha256', 'documents', ['sha256'])
    
    # 6. Удаляем старый неуникальный индекс sha256
    op.drop_index('idx_documents_sha256', table_name='documents')
    op.drop_index('ix_documents_sha256', table_name='documents')


def downgrade() -> None:
    # Откат к новой схеме (обратное преобразование)
    op.drop_constraint('uq_documents_sha256', 'documents', type_='unique')
    op.create_index('idx_documents_sha256', 'documents', ['sha256'])
    
    op.drop_column('documents', 'created_at')
    op.drop_column('documents', 'last_accessed_at')
    op.drop_column('documents', 'indexing_cost_seconds')
    op.drop_column('documents', 'access_count')
    op.drop_column('documents', 'parse_status')
    
    op.alter_column('documents', 'mime', new_column_name='content_type', existing_type=sa.String(127))
    
    op.add_column('documents', sa.Column('indexed_at', sa.DateTime(), nullable=True))
    op.add_column('documents', sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
    op.add_column('documents', sa.Column('status', sa.Enum('new', 'parsed', 'indexed', 'error', name='document_status'), nullable=False, server_default='new'))
    op.add_column('documents', sa.Column('storage_url', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('blob', sa.LargeBinary(), nullable=True))
    op.add_column('documents', sa.Column('original_filename', sa.String(512), nullable=False, server_default='unknown'))
    op.add_column('documents', sa.Column('owner_id', sa.Integer(), nullable=False, server_default='1'))
    
    op.create_foreign_key('documents_owner_id_fkey', 'documents', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_documents_owner_status', 'documents', ['owner_id', 'status'])
