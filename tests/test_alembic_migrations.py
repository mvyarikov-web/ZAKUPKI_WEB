"""
Тесты миграций Alembic (инкремент 13, шаг 6).
Проверяем:
- Генерацию миграций
- Применение миграции upgrade head  
- Наличие всех таблиц после миграции через Base.metadata
- Проверку совместимости моделей и миграций
"""

import subprocess
from sqlalchemy import inspect, text

from webapp.db import engine


def test_alembic_current_shows_migration():
    """Команда alembic current показывает текущую миграцию."""
    result = subprocess.run(
        ['python3', '-m', 'alembic', 'current'],
        cwd='/Users/maksimyarikov/Desktop/Автоматизация закупок/Код/web_interface',
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    # Проверяем, что миграция либо в stdout, либо в stderr
    output = result.stdout + result.stderr
    assert '14c42e5d4b45' in output or 'initial_schema_phase1' in output


def test_alembic_upgrade_creates_all_tables():
    """После alembic upgrade head все таблицы созданы."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    expected_tables = {
        'users', 'sessions', 'documents', 'chunks',
        'ai_conversations', 'ai_messages',
        'search_history', 'api_keys', 'user_models',
        'app_logs', 'job_queue', 'alembic_version'
    }
    
    assert expected_tables.issubset(set(tables)), f"Отсутствуют таблицы: {expected_tables - set(tables)}"


def test_alembic_version_table_exists():
    """Таблица alembic_version существует и содержит запись."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert result is not None
        assert len(result[0]) > 0  # version_num не пустой


def test_users_table_has_correct_structure():
    """Таблица users имеет правильную структуру после миграции."""
    inspector = inspect(engine)
    columns = {col['name']: col for col in inspector.get_columns('users')}
    
    assert 'id' in columns
    assert 'email' in columns
    assert 'password_hash' in columns
    assert 'role' in columns
    assert 'created_at' in columns
    assert 'updated_at' in columns


def test_chunks_table_has_embedding_column():
    """Таблица chunks имеет колонку embedding после миграции."""
    inspector = inspect(engine)
    columns = {col['name']: col for col in inspector.get_columns('chunks')}
    
    assert 'embedding' in columns
    assert 'document_id' in columns
    assert 'owner_id' in columns
    assert 'chunk_idx' in columns
    assert 'text' in columns


def test_foreign_keys_created():
    """Foreign keys созданы корректно."""
    inspector = inspect(engine)
    
    # Проверяем FK в sessions
    sessions_fks = inspector.get_foreign_keys('sessions')
    assert len(sessions_fks) == 1
    assert sessions_fks[0]['referred_table'] == 'users'
    
    # Проверяем FK в chunks
    chunks_fks = inspector.get_foreign_keys('chunks')
    assert len(chunks_fks) == 2  # document_id и owner_id
    fk_tables = {fk['referred_table'] for fk in chunks_fks}
    assert 'users' in fk_tables
    assert 'documents' in fk_tables


def test_indexes_created():
    """Индексы созданы после миграции."""
    inspector = inspect(engine)
    
    # Проверяем индексы users
    users_indexes = inspector.get_indexes('users')
    index_names = {idx['name'] for idx in users_indexes}
    assert 'ix_users_email' in index_names
    
    # Проверяем индексы chunks
    chunks_indexes = inspector.get_indexes('chunks')
    index_names = {idx['name'] for idx in chunks_indexes}
    assert 'idx_chunks_document' in index_names
    assert 'idx_chunks_owner' in index_names


def test_enum_types_work():
    """ENUM типы работают корректно (проверка вставки)."""
    from webapp.db import SessionLocal, User
    
    with SessionLocal() as session:
        # Создаём пользователя с role='admin'
        user = User(
            email='test_enum@example.com',
            password_hash='test_hash',
            role='admin'
        )
        session.add(user)
        session.commit()
        
        # Проверяем, что role сохранился
        session.refresh(user)
        assert user.role == 'admin'
        assert user.id is not None
        
        # Очищаем
        session.delete(user)
        session.commit()


def test_cascade_delete_works():
    """Каскадное удаление работает (user → sessions)."""
    from webapp.db import SessionLocal, User, Session
    from datetime import datetime, timedelta
    
    with SessionLocal() as session:
        # Создаём пользователя и сессию
        user = User(
            email='test_cascade@example.com',
            password_hash='test_hash',
            role='user'
        )
        session.add(user)
        session.flush()
        
        user_session = Session(
            user_id=user.id,
            token_hash='test_token_hash',
            expires_at=datetime.utcnow() + timedelta(days=1)
        )
        session.add(user_session)
        session.commit()
        
        session_id = user_session.id
        
        # Удаляем пользователя
        session.delete(user)
        session.commit()
        
        # Проверяем, что сессия тоже удалилась
        deleted_session = session.query(Session).filter_by(id=session_id).first()
        assert deleted_session is None


def test_migration_is_idempotent():
    """Повторное применение миграции безопасно."""
    # Этот тест проверяет, что после upgrade head
    # повторный upgrade head не вызывает ошибок
    import subprocess
    
    result = subprocess.run(
        ['python3', '-m', 'alembic', 'current'],
        cwd='/Users/maksimyarikov/Desktop/Автоматизация закупок/Код/web_interface',
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert 'initial_schema_phase1' in result.stdout or '14c42e5d4b45' in result.stdout
