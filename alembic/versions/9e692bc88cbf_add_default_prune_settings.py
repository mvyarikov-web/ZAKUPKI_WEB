"""add_default_prune_settings

Revision ID: 9e692bc88cbf
Revises: 1a8da9c55a1f
Create Date: 2025-11-11 06:27:47.862323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e692bc88cbf'
down_revision: Union[str, None] = '1a8da9c55a1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавить дефолтные настройки для автоматической очистки БД."""
    # Вставляем AUTO_PRUNE_ENABLED (по умолчанию включён)
    op.execute("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('AUTO_PRUNE_ENABLED', 'true', NOW())
        ON CONFLICT (key) DO NOTHING
    """)
    
    # Вставляем DB_SIZE_LIMIT_BYTES (по умолчанию 10 ГБ)
    op.execute("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('DB_SIZE_LIMIT_BYTES', '10737418240', NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    """Удалить настройки прунинга."""
    op.execute("DELETE FROM app_settings WHERE key IN ('AUTO_PRUNE_ENABLED', 'DB_SIZE_LIMIT_BYTES')")
