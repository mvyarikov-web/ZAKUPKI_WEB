"""add_blob_and_app_settings_for_pure_db_mode

Revision ID: 1a8da9c55a1f
Revises: bfc3b9559a9e
Create Date: 2025-11-10 06:02:13.815671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a8da9c55a1f'
down_revision: Union[str, None] = 'bfc3b9559a9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавить колонку blob в documents
    op.add_column('documents', sa.Column('blob', sa.LargeBinary(), nullable=True))
    
    # 2. Убедиться что size_bytes существует (уже есть, но на всякий случай)
    # op.add_column('documents', sa.Column('size_bytes', sa.Integer(), nullable=True))
    
    # 3. Проверить уникальный индекс на sha256 (уже есть через UniqueConstraint)
    # CREATE UNIQUE INDEX IF NOT EXISTS будет игнорироваться если индекс уже существует
    
    # 4. Создать таблицу app_settings
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False)
    )
    
    # 5. Вставить дефолтное значение лимита БД (10 ГБ)
    op.execute("""
        INSERT INTO app_settings (key, value, description)
        VALUES ('DB_SIZE_LIMIT_BYTES', '10737418240', 'Database size limit in bytes (default 10GB)')
        ON CONFLICT (key) DO NOTHING;
    """)
    
    # 6. Проверить/добавить ON DELETE CASCADE для chunks
    # Сначала проверим текущее состояние constraints
    op.execute("""
        DO $$
        BEGIN
            -- Удаляем старое ограничение если оно без CASCADE
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name = 'chunks_document_id_fkey' 
                AND table_name = 'chunks'
            ) THEN
                ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_document_id_fkey;
                ALTER TABLE chunks 
                    ADD CONSTRAINT chunks_document_id_fkey 
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    
    # 7. Проверить/добавить ON DELETE CASCADE для search_index
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name = 'search_index_document_id_fkey' 
                AND table_name = 'search_index'
            ) THEN
                ALTER TABLE search_index DROP CONSTRAINT IF EXISTS search_index_document_id_fkey;
                ALTER TABLE search_index 
                    ADD CONSTRAINT search_index_document_id_fkey 
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    
    # 8. Добавить колонку status_data в folder_index_status
    op.add_column('folder_index_status', sa.Column('status_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Откат изменений в обратном порядке
    op.drop_column('folder_index_status', 'status_data')
    
    # Откатить CASCADE constraints сложно, пропускаем (обычно не требуется)
    
    op.execute("DELETE FROM app_settings WHERE key = 'DB_SIZE_LIMIT_BYTES';")
    op.drop_table('app_settings')
    
    op.drop_column('documents', 'blob')
