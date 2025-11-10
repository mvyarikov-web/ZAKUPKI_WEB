"""add_search_index_table

Добавляет таблицу search_index для хранения поискового индекса в БД.
Заменяет файловый индекс _search_index.txt.

Revision ID: 5ffc684e6693
Revises: legacy_to_db_001
Create Date: 2025-11-10 02:19:36.003890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5ffc684e6693'
down_revision: Union[str, None] = 'legacy_to_db_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт таблицу search_index для полнотекстового поиска."""
    
    # Создаём таблицу search_index
    op.create_table(
        'search_index',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True),  # для полнотекстового поиска
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Индексы для быстрого поиска
    op.create_index('idx_search_index_document', 'search_index', ['document_id'])
    op.create_index('idx_search_index_user', 'search_index', ['user_id'])
    op.create_index('idx_search_index_created', 'search_index', ['created_at'])
    
    # GIN индекс для полнотекстового поиска (PostgreSQL)
    op.execute("""
        CREATE INDEX idx_search_index_search_vector 
        ON search_index 
        USING GIN(search_vector);
    """)
    
    # Триггер для автоматического обновления search_vector
    op.execute("""
        CREATE OR REPLACE FUNCTION search_index_tsvector_trigger() 
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('russian', COALESCE(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER tsvector_update_trigger
        BEFORE INSERT OR UPDATE ON search_index
        FOR EACH ROW
        EXECUTE FUNCTION search_index_tsvector_trigger();
    """)


def downgrade() -> None:
    """Удаляет таблицу search_index и связанные объекты."""
    
    # Удаляем триггер и функцию
    op.execute('DROP TRIGGER IF EXISTS tsvector_update_trigger ON search_index;')
    op.execute('DROP FUNCTION IF EXISTS search_index_tsvector_trigger();')
    
    # Удаляем таблицу (индексы удалятся автоматически)
    op.drop_table('search_index')
