"""Миграция legacy файловых данных в БД

Revision ID: legacy_to_db_001
Revises: 14c42e5d4b45
Create Date: 2025-11-09

Добавляет таблицы для хранения:
- ai_model_configs: конфигурация AI моделей (замена models.json)
- file_search_state: состояния файлов при поиске (замена search_results.json)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'legacy_to_db_001'
down_revision = '14c42e5d4b45'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет таблицы для замены legacy файлов."""
    
    # Таблица для конфигурации AI моделей (замена models.json)
    op.create_table(
        'ai_model_configs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('model_id', sa.String(127), nullable=False, unique=True, index=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('provider', sa.String(63), nullable=False),  # openai, perplexity, deepseek, etc.
        sa.Column('context_window_tokens', sa.Integer(), nullable=False, default=4096),
        sa.Column('max_output_tokens', sa.Integer()),
        sa.Column('price_input_per_1m', sa.Numeric(10, 6), default=0.0),
        sa.Column('price_output_per_1m', sa.Numeric(10, 6), default=0.0),
        sa.Column('price_per_1000_requests', sa.Numeric(10, 6)),  # для моделей с посчётом за запросы
        sa.Column('pricing_model', sa.String(31), default='per_token'),  # per_token или per_request
        sa.Column('supports_system_role', sa.Boolean(), default=True),
        sa.Column('supports_streaming', sa.Boolean(), default=True),
        sa.Column('supports_function_calling', sa.Boolean(), default=False),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('timeout_seconds', sa.Integer(), default=60),
        sa.Column('config_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),  # дополнительные настройки
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Индексы для быстрого поиска
    op.create_index('idx_ai_model_configs_provider_enabled', 'ai_model_configs', ['provider', 'is_enabled'])
    op.create_index('idx_ai_model_configs_default', 'ai_model_configs', ['is_default'])
    
    # Таблица для состояний файлов при поиске (замена search_results.json)
    op.create_table(
        'file_search_state',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),  # относительный путь от uploads/
        sa.Column('status', sa.String(63), nullable=False),  # not_checked, processing, contains_keywords, no_keywords, error
        sa.Column('search_terms', sa.Text()),  # последние поисковые термины
        sa.Column('result_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),  # детали результата
        sa.Column('last_checked_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Индексы для быстрого доступа
    op.create_index('idx_file_search_state_user_file', 'file_search_state', ['user_id', 'file_path'], unique=True)
    op.create_index('idx_file_search_state_status', 'file_search_state', ['status'])
    op.create_index('idx_file_search_state_updated', 'file_search_state', ['updated_at'])


def downgrade() -> None:
    """Удаляет таблицы."""
    op.drop_table('file_search_state')
    op.drop_table('ai_model_configs')
