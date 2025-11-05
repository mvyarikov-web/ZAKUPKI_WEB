"""
Интеграционные тесты для PostgreSQL (инкремент 13, шаг 6).
Проверяют работу с реальной БД PostgreSQL.

Запуск: pytest tests/test_postgres_integration.py -v
"""

import pytest
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# Загружаем .env с переопределением
load_dotenv(override=True)

from webapp.db import SessionLocal, User, Session as UserSession, Document, Chunk  # noqa: E402


@pytest.fixture(scope='module')
def postgres_engine():
    """Создаём движок для PostgreSQL из .env."""
    db_url = os.getenv('DATABASE_URL')
    if not db_url or 'postgresql' not in db_url:
        pytest.skip("PostgreSQL DATABASE_URL не настроен в .env")
    
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope='module')
def postgres_session(postgres_engine):
    """Создаём сессию для PostgreSQL."""
    # Используем SessionLocal, который уже настроен на PostgreSQL
    session = SessionLocal()
    yield session
    session.close()


def test_postgres_connection(postgres_engine):
    """Проверка подключения к PostgreSQL."""
    with postgres_engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        assert 'PostgreSQL' in version
        print(f"\n✅ PostgreSQL version: {version[:50]}")


def test_pgvector_extension_installed(postgres_engine):
    """Проверка установки расширения pgvector."""
    with postgres_engine.connect() as conn:
        result = conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        assert row is not None, "pgvector не установлен"
        assert row[0] == 'vector'
        print(f"\n✅ pgvector version: {row[1]}")


def test_all_tables_exist(postgres_engine):
    """Проверка наличия всех таблиц после миграции."""
    inspector = inspect(postgres_engine)
    tables = set(inspector.get_table_names())
    
    expected_tables = {
        'users', 'sessions', 'documents', 'chunks',
        'ai_conversations', 'ai_messages',
        'search_history', 'api_keys', 'user_models',
        'app_logs', 'job_queue', 'alembic_version'
    }
    
    assert expected_tables.issubset(tables), f"Отсутствуют таблицы: {expected_tables - tables}"
    print(f"\n✅ Все {len(expected_tables)} таблиц созданы")


def test_embedding_column_is_vector(postgres_engine):
    """Проверка, что колонка embedding имеет тип vector."""
    with postgres_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, udt_name 
            FROM information_schema.columns 
            WHERE table_name = 'chunks' AND column_name = 'embedding'
        """))
        row = result.fetchone()
        assert row is not None, "Колонка embedding не найдена"
        assert row[1] == 'vector', f"Неправильный тип колонки: {row[1]}"
        print("\n✅ Колонка embedding имеет тип vector")


def test_create_user(postgres_session):
    """Создание пользователя в PostgreSQL."""
    user = User(
        email='test_integration@example.com',
        password_hash='hashed_password_123',
        role='user'
    )
    postgres_session.add(user)
    postgres_session.commit()
    
    assert user.id is not None
    assert user.created_at is not None
    print(f"\n✅ Пользователь создан с ID: {user.id}")
    
    # Очистка
    postgres_session.delete(user)
    postgres_session.commit()


def test_create_session_with_cascade(postgres_session):
    """Создание сессии с проверкой каскадного удаления."""
    user = User(
        email='test_cascade@example.com',
        password_hash='hash',
        role='user'
    )
    postgres_session.add(user)
    postgres_session.flush()
    
    session = UserSession(
        user_id=user.id,
        token_hash='test_token_hash_123',
        expires_at=datetime.utcnow() + timedelta(days=1)
    )
    postgres_session.add(session)
    postgres_session.commit()
    
    session_id = session.id
    
    # Удаляем пользователя
    postgres_session.delete(user)
    postgres_session.commit()
    
    # Проверяем, что сессия тоже удалилась (CASCADE)
    deleted_session = postgres_session.query(UserSession).filter_by(id=session_id).first()
    assert deleted_session is None, "Каскадное удаление не сработало"
    print("\n✅ Каскадное удаление работает корректно")


def test_enum_types_in_postgres(postgres_session):
    """Проверка работы ENUM типов."""
    # Создаём пользователя с role='admin'
    user = User(
        email='test_enum@example.com',
        password_hash='hash',
        role='admin'
    )
    postgres_session.add(user)
    postgres_session.commit()
    
    postgres_session.refresh(user)
    assert user.role == 'admin'
    print(f"\n✅ ENUM тип role работает корректно: {user.role}")
    
    # Очистка
    postgres_session.delete(user)
    postgres_session.commit()


def test_document_and_chunks(postgres_session):
    """Создание документа и чанков."""
    user = User(
        email='test_doc@example.com',
        password_hash='hash',
        role='user'
    )
    postgres_session.add(user)
    postgres_session.flush()
    
    doc = Document(
        owner_id=user.id,
        original_filename='test.pdf',
        content_type='application/pdf',
        size_bytes=1024,
        sha256='abc123',
        status='new'
    )
    postgres_session.add(doc)
    postgres_session.flush()
    
    chunk = Chunk(
        document_id=doc.id,
        owner_id=user.id,
        chunk_idx=0,
        text='Test text for chunk',
        # embedding будет NULL (для теста без реального вектора)
    )
    postgres_session.add(chunk)
    postgres_session.commit()
    
    assert chunk.id is not None
    assert chunk.document_id == doc.id
    print("\n✅ Документ и чанк созданы успешно")
    
    # Очистка (CASCADE удалит chunk автоматически)
    postgres_session.delete(doc)
    postgres_session.delete(user)
    postgres_session.commit()


def test_alembic_version_recorded(postgres_engine):
    """Проверка записи версии миграции."""
    with postgres_engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.fetchone()
        assert version is not None
        assert version[0] == '14c42e5d4b45'
        print(f"\n✅ Alembic версия: {version[0]}")
