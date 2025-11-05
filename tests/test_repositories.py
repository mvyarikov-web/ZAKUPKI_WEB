"""
Тесты для репозиториев (Data Access Layer).

Базовые тесты для проверки CRUD операций.
Используют in-memory SQLite для быстрого тестирования.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from webapp.db.base import Base
from webapp.db.models import UserRole, DocumentStatus
from webapp.db.repositories import UserRepository, DocumentRepository, ChunkRepository


@pytest.fixture
def engine():
    """In-memory SQLite engine для тестов."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """Сессия БД для каждого теста."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def user_repo(session):
    """UserRepository fixture."""
    return UserRepository(session)


@pytest.fixture
def doc_repo(session):
    """DocumentRepository fixture."""
    return DocumentRepository(session)


@pytest.fixture
def chunk_repo(session):
    """ChunkRepository fixture."""
    return ChunkRepository(session)


@pytest.fixture
def sample_user(user_repo):
    """Создать тестового пользователя."""
    return user_repo.create_user(
        email="test@example.com",
        password_hash="$2b$12$fakehashfakehashfakehash",
        role=UserRole.USER
    )


@pytest.fixture
def sample_document(doc_repo, sample_user):
    """Создать тестовый документ."""
    return doc_repo.create_document(
        owner_id=sample_user.id,
        original_filename="test.pdf",
        size_bytes=1024,
        sha256="abc123" * 10 + "abcd",  # 64 символа
        content_type="application/pdf"
    )


# ===== UserRepository Tests =====

def test_user_create(user_repo):
    """Тест создания пользователя."""
    user = user_repo.create_user(
        email="new@example.com",
        password_hash="$2b$12$hash123"
    )
    assert user.id is not None
    assert user.email == "new@example.com"
    assert user.role == UserRole.USER.value


def test_user_get_by_email(user_repo, sample_user):
    """Тест получения пользователя по email."""
    user = user_repo.get_by_email("test@example.com")
    assert user is not None
    assert user.id == sample_user.id
    assert user.email == sample_user.email


def test_user_update_password(user_repo, sample_user):
    """Тест обновления пароля."""
    new_hash = "$2b$12$newhashnewhash"
    updated = user_repo.update_password(sample_user.id, new_hash)
    assert updated is not None
    assert updated.password_hash == new_hash


# ===== DocumentRepository Tests =====

def test_document_create(doc_repo, sample_user):
    """Тест создания документа."""
    doc = doc_repo.create_document(
        owner_id=sample_user.id,
        original_filename="new.docx",
        size_bytes=2048,
        sha256="xyz789" * 10 + "1234"  # 64 символа
    )
    assert doc.id is not None
    assert doc.owner_id == sample_user.id
    assert doc.original_filename == "new.docx"
    assert doc.status == DocumentStatus.PENDING.value


def test_document_get_by_owner(doc_repo, sample_user, sample_document):
    """Тест получения документов владельца."""
    doc_repo.create_document(
        sample_user.id, "doc2.txt", 512, "hash2" * 16
    )
    docs = doc_repo.get_by_owner(sample_user.id)
    assert len(docs) == 2
    assert all(d.owner_id == sample_user.id for d in docs)


def test_document_update_status(doc_repo, sample_document):
    """Тест обновления статуса."""
    updated = doc_repo.update_status(sample_document.id, DocumentStatus.PROCESSING)
    assert updated is not None
    assert updated.status == DocumentStatus.PROCESSING.value


def test_document_mark_indexed(doc_repo, sample_document):
    """Тест пометки документа как проиндексированного."""
    marked = doc_repo.mark_indexed(sample_document.id, chunk_count=10)
    assert marked is not None
    assert marked.status == DocumentStatus.INDEXED.value
    assert marked.indexed_at is not None


# ===== ChunkRepository Tests =====

def test_chunk_create(chunk_repo, sample_document, sample_user):
    """Тест создания чанка."""
    chunk = chunk_repo.create_chunk(
        document_id=sample_document.id,
        owner_id=sample_user.id,
        text="Sample text chunk",
        chunk_idx=0
    )
    assert chunk.id is not None
    assert chunk.document_id == sample_document.id
    assert chunk.owner_id == sample_user.id
    assert chunk.text == "Sample text chunk"
    assert chunk.chunk_idx == 0


def test_chunk_get_by_document(chunk_repo, sample_document, sample_user):
    """Тест получения чанков документа."""
    chunk_repo.create_chunk(sample_document.id, sample_user.id, "Chunk 1", 0)
    chunk_repo.create_chunk(sample_document.id, sample_user.id, "Chunk 2", 1)
    chunk_repo.create_chunk(sample_document.id, sample_user.id, "Chunk 3", 2)
    
    chunks = chunk_repo.get_by_document(sample_document.id)
    assert len(chunks) == 3
    # Проверка сортировки по chunk_idx
    assert chunks[0].chunk_idx == 0
    assert chunks[1].chunk_idx == 1
    assert chunks[2].chunk_idx == 2


def test_chunk_count_by_document(chunk_repo, sample_document, sample_user):
    """Тест подсчёта чанков."""
    chunk_repo.create_chunk(sample_document.id, sample_user.id, "C1", 0)
    chunk_repo.create_chunk(sample_document.id, sample_user.id, "C2", 1)
    
    count = chunk_repo.count_by_document(sample_document.id)
    assert count == 2


# ===== BaseRepository Tests =====

def test_base_repo_get_all(user_repo):
    """Тест получения всех записей."""
    user_repo.create_user("u1@test.com", "h1")
    user_repo.create_user("u2@test.com", "h2")
    user_repo.create_user("u3@test.com", "h3")
    
    all_users = user_repo.get_all()
    assert len(all_users) == 3


def test_base_repo_exists(user_repo, sample_user):
    """Тест проверки существования."""
    assert user_repo.exists(email="test@example.com") is True
    assert user_repo.exists(email="notfound@example.com") is False


def test_base_repo_delete(user_repo, sample_user):
    """Тест удаления записи."""
    deleted = user_repo.delete(sample_user.id)
    assert deleted is True
    
    user = user_repo.get_by_id(sample_user.id)
    assert user is None
