"""add_status_data_to_folder_index_status

Revision ID: 209c1dea59f0
Revises: 9e692bc88cbf
Create Date: 2025-11-11 07:09:11.558218

Блок 7: Статусы индексации в БД
Добавляем колонку status_data JSONB для хранения прогресса индексации.
Больше не используем index/status.json.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '209c1dea59f0'
down_revision: Union[str, None] = '9e692bc88cbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавить колонку status_data JSONB в folder_index_status."""
    # Проверяем, не существует ли уже колонка (для идемпотентности)
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'folder_index_status' 
        AND column_name = 'status_data'
    """))
    
    if result.fetchone() is None:
        # Колонка не существует - добавляем
        op.add_column('folder_index_status',
                      sa.Column('status_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        print("✅ Колонка status_data добавлена в folder_index_status")
    else:
        print("⏭️  Колонка status_data уже существует - пропускаем")


def downgrade() -> None:
    """Удалить колонку status_data из folder_index_status."""
    op.drop_column('folder_index_status', 'status_data')
