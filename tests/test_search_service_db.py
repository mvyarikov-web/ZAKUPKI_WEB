"""
Тесты для SearchService и гибридного поиска.

Проверяет keyword, semantic, hybrid search и историю.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from webapp.db.base import Base
from webapp.db.repositories import ChunkRepository, SearchHistoryRepository
from webapp.services.search_service import SearchService


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
def search_service(test_db_session):
    """Создаёт SearchService."""
    chunk_repo = ChunkRepository(test_db_session)
    history_repo = SearchHistoryRepository(test_db_session)
    return SearchService(chunk_repo, history_repo)


@pytest.fixture
def test_data(test_db_session):
    """Создаёт тестовые данные: пользователь, документ, чанки."""
    from webapp.db.models import User, UserRole, Document, Chunk
    
    # Пользователь
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Документ
    document = Document(
        owner_id=user.id,
        original_filename="test.txt",
        size_bytes=100,
        sha256="abc123",
        status='indexed'
    )
    test_db_session.add(document)
    test_db_session.commit()
    
    # Чанки с разным содержимым
    chunks_data = [
        {
            'document_id': document.id,
            'owner_id': user.id,
            'text': 'Python is a programming language. It is widely used for web development.',
            'chunk_idx': 0,
            'embedding': [0.1] * 1536
        },
        {
            'document_id': document.id,
            'owner_id': user.id,
            'text': 'JavaScript is another popular programming language for web applications.',
            'chunk_idx': 1,
            'embedding': [0.2] * 1536
        },
        {
            'document_id': document.id,
            'owner_id': user.id,
            'text': 'Machine learning uses Python extensively for data analysis.',
            'chunk_idx': 2,
            'embedding': [0.3] * 1536
        }
    ]
    
    for data in chunks_data:
        chunk = Chunk(**data)
        test_db_session.add(chunk)
    
    test_db_session.commit()
    
    return {
        'user': user,
        'document': document
    }


def test_make_snippet():
    """Тест создания сниппета."""
    text = "This is a long text with multiple sentences. We want to find the query word."
    query = "query"
    
    snippet = SearchService.make_snippet(text, query, length=50)
    
    assert "query" in snippet.lower()
    assert len(snippet) <= 60  # С учётом "..."


def test_keyword_search(search_service, test_data, test_db_session):
    """Тест полнотекстового поиска."""
    results = search_service.keyword_search(
        query="Python",
        user_id=test_data['user'].id,
        limit=10
    )
    
    assert len(results) == 2  # Два чанка содержат "Python"
    assert all("python" in r.chunk.text.lower() for r in results)
    assert all(r.score > 0 for r in results)


@pytest.mark.skip(reason="SQLite не поддерживает pgvector операторы - только для PostgreSQL")
@patch('openai.embeddings.create')
def test_semantic_search(mock_create, search_service, test_data, test_db_session):
    """Тест векторного поиска с mock OpenAI."""
    # Mock OpenAI response
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.15] * 1536)]
    mock_create.return_value = mock_response
    
    results = search_service.semantic_search(
        query="programming language",
        user_id=test_data['user'].id,
        limit=5,
        min_similarity=0.0
    )
    
    assert len(results) > 0
    assert all(hasattr(r, 'score') for r in results)
    assert all(hasattr(r, 'snippet') for r in results)


@pytest.mark.skip(reason="SQLite не поддерживает pgvector операторы - только для PostgreSQL")
@patch('openai.embeddings.create')
def test_hybrid_search(mock_create, search_service, test_data, test_db_session):
    """Тест гибридного поиска."""
    # Mock OpenAI
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.15] * 1536)]
    mock_create.return_value = mock_response
    
    results = search_service.hybrid_search(
        query="Python",
        user_id=test_data['user'].id,
        limit=5,
        keyword_weight=0.5,
        semantic_weight=0.5
    )
    
    assert len(results) > 0
    # Результаты должны быть отсортированы по score
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_save_to_history(search_service, test_data, test_db_session):
    """Тест сохранения в историю поиска."""
    search_service.save_to_history(
        user_id=test_data['user'].id,
        query="test query",
        results_count=5,
        filters={'mode': 'hybrid'}
    )
    
    # Проверяем, что запись создана
    history_repo = SearchHistoryRepository(test_db_session)
    history = history_repo.get_by_user(test_data['user'].id)
    
    assert len(history) == 1
    assert history[0].query_text == "test query"
    assert history[0].results_count == 5


def test_search_history_recent(test_db_session, test_data):
    """Тест получения последних запросов."""
    history_repo = SearchHistoryRepository(test_db_session)
    
    # Создаём несколько запросов
    for i in range(5):
        history_repo.create_search_record(
            user_id=test_data['user'].id,
            query_text=f"query {i}",
            results_count=i
        )
    
    # Получаем последние 3
    recent = history_repo.get_recent(test_data['user'].id, limit=3)
    
    assert len(recent) == 3
    # Проверяем порядок (новые первые)
    assert recent[0].query_text == "query 4"
    assert recent[1].query_text == "query 3"
    assert recent[2].query_text == "query 2"


def test_search_history_delete_old(test_db_session, test_data):
    """Тест удаления старых записей."""
    from datetime import datetime, timedelta
    
    history_repo = SearchHistoryRepository(test_db_session)
    
    # Создаём старую запись (вручную ставим дату)
    old_record = history_repo.create_search_record(
        user_id=test_data['user'].id,
        query_text="old query",
        results_count=1
    )
    old_record.created_at = datetime.utcnow() - timedelta(days=40)
    test_db_session.commit()
    
    # Создаём новую запись
    history_repo.create_search_record(
        user_id=test_data['user'].id,
        query_text="new query",
        results_count=1
    )
    
    # Удаляем записи старше 30 дней
    deleted = history_repo.delete_old(days=30)
    
    assert deleted == 1
    
    # Проверяем, что осталась только новая запись
    remaining = history_repo.get_by_user(test_data['user'].id)
    assert len(remaining) == 1
    assert remaining[0].query_text == "new query"


def test_search_result_to_dict(test_data, test_db_session):
    """Тест сериализации SearchResult в dict."""
    from webapp.services.search_service import SearchResult
    from webapp.db.models import Chunk
    
    chunk = test_db_session.query(Chunk).first()
    
    result = SearchResult(
        chunk=chunk,
        score=0.95,
        snippet="Test snippet",
        document_id=test_data['document'].id,
        document_name="test.txt"
    )
    
    result_dict = result.to_dict()
    
    assert result_dict['chunk_id'] == chunk.id
    assert result_dict['score'] == 0.95
    assert result_dict['snippet'] == "Test snippet"
    assert result_dict['document_name'] == "test.txt"
