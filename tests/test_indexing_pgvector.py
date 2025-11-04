"""
Тесты для IndexingService и pgvector.

Проверяет извлечение текста, чанкинг, генерацию embeddings и сохранение в chunks.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from webapp.db.base import Base
from webapp.db.repositories import DocumentRepository, ChunkRepository
from webapp.services.indexing_service import IndexingService


@pytest.fixture(scope='function')
def test_db_session():
    """Создаёт изолированную тестовую БД в памяти."""
    test_engine = create_engine(
        'sqlite:///:memory:',
        echo=False,
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def indexing_service(test_db_session):
    """Создаёт IndexingService без реального OpenAI API."""
    doc_repo = DocumentRepository(test_db_session)
    chunk_repo = ChunkRepository(test_db_session)
    return IndexingService(doc_repo, chunk_repo)


def test_extract_text_from_blob(indexing_service, test_db_session):
    """Тест извлечения текста из blob."""
    from webapp.db.models import User, UserRole, Document
    
    # Создаём пользователя
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Создаём документ с текстом
    text = "Это тестовый документ. Он содержит несколько предложений."
    document = Document(
        owner_id=user.id,
        original_filename="test.txt",
        size_bytes=len(text.encode('utf-8')),
        sha256="abc123",
        blob=text.encode('utf-8'),
        status='new'
    )
    test_db_session.add(document)
    test_db_session.commit()
    
    # Извлекаем текст
    extracted = IndexingService.extract_text_from_blob(document)
    assert extracted == text


def test_split_into_chunks():
    """Тест разбивки текста на чанки."""
    text = "Первое предложение. Второе предложение. Третье предложение. Четвёртое предложение."
    
    chunks = IndexingService.split_into_chunks(text, chunk_size=50)
    
    assert len(chunks) > 0
    assert all(isinstance(chunk, str) for chunk in chunks)
    assert all(len(chunk) <= 50 or '.' not in chunk for chunk in chunks)


def test_calculate_text_hash():
    """Тест расчёта SHA256 хэша текста."""
    text = "Test text"
    hash1 = IndexingService.calculate_text_hash(text)
    hash2 = IndexingService.calculate_text_hash(text)
    
    assert len(hash1) == 64
    assert hash1 == hash2  # Идемпотентность
    
    # Разный текст = разный хэш
    hash3 = IndexingService.calculate_text_hash("Different text")
    assert hash1 != hash3


@patch('openai.embeddings.create')
def test_generate_embeddings_mock(mock_create, indexing_service):
    """Тест генерации embeddings с mock OpenAI."""
    # Настраиваем mock
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
        Mock(embedding=[0.2] * 1536)
    ]
    mock_create.return_value = mock_response
    
    texts = ["First chunk", "Second chunk"]
    embeddings = indexing_service.generate_embeddings(texts)
    
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 1536
    assert len(embeddings[1]) == 1536


@patch('openai.embeddings.create')
def test_index_document(mock_create, indexing_service, test_db_session):
    """Тест полной индексации документа."""
    from webapp.db.models import User, UserRole, Document
    
    # Mock OpenAI
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
        Mock(embedding=[0.2] * 1536)
    ]
    mock_create.return_value = mock_response
    
    # Создаём пользователя
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Создаём документ
    text = "Это первый чанк. " * 50 + "Это второй чанк. " * 50
    document = Document(
        owner_id=user.id,
        original_filename="test.txt",
        size_bytes=len(text.encode('utf-8')),
        sha256="abc123",
        blob=text.encode('utf-8'),
        status='new'
    )
    test_db_session.add(document)
    test_db_session.commit()
    
    # Индексируем
    chunks_count, error = indexing_service.index_document(document.id)
    
    assert error is None
    assert chunks_count > 0
    
    # Проверяем, что чанки созданы
    chunk_repo = ChunkRepository(test_db_session)
    chunks = chunk_repo.get_by_document(document.id)
    
    assert len(chunks) == chunks_count
    assert all(chunk.embedding is not None for chunk in chunks)
    assert all(chunk.text_sha256 is not None for chunk in chunks)


@patch('openai.embeddings.create')
def test_reindex_document(mock_create, indexing_service, test_db_session):
    """Тест переиндексации документа (удаление старых чанков)."""
    from webapp.db.models import User, UserRole, Document
    
    # Mock OpenAI
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1] * 1536)]
    mock_create.return_value = mock_response
    
    # Создаём пользователя
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Создаём документ
    text = "Короткий тестовый текст."
    document = Document(
        owner_id=user.id,
        original_filename="test.txt",
        size_bytes=len(text.encode('utf-8')),
        sha256="abc123",
        blob=text.encode('utf-8'),
        status='new'
    )
    test_db_session.add(document)
    test_db_session.commit()
    
    # Первая индексация
    count1, _ = indexing_service.index_document(document.id)
    
    # Переиндексация
    count2, _ = indexing_service.index_document(document.id, reindex=True)
    
    # Проверяем, что старые чанки удалены
    chunk_repo = ChunkRepository(test_db_session)
    chunks = chunk_repo.get_by_document(document.id)
    
    assert len(chunks) == count2


def test_index_document_not_found(indexing_service):
    """Тест индексации несуществующего документа."""
    chunks_count, error = indexing_service.index_document(999999)
    
    assert chunks_count == 0
    assert error is not None
    assert "не найден" in error
