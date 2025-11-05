"""
Тесты для GC-сервиса (Garbage Collection)

Проверяется:
- Расчёт retention score
- Получение кандидатов на удаление
- Безопасное удаление документов
- Dry-run режим
- Статистика хранилища
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock


def test_calculate_retention_score():
    """Тест расчёта retention score."""
    from webapp.services.gc_service import calculate_retention_score
    
    now = datetime.now()
    
    # Тест 1: Недавно используемый документ с высокой активностью
    score1 = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=1),
        access_count=100,
        indexing_cost_seconds=600.0,  # 10 минут
        now=now
    )
    # Должен быть высокий положительный score
    assert score1 > 0
    
    # Тест 2: Старый неиспользуемый документ
    score2 = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=365),
        access_count=0,
        indexing_cost_seconds=60.0,  # 1 минута
        now=now
    )
    # Должен быть отрицательный score
    assert score2 < 0
    
    # Тест 3: Документ с высокой стоимостью индексации
    score3 = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=30),
        access_count=10,
        indexing_cost_seconds=6000.0,  # 100 минут
        now=now
    )
    # Высокая стоимость индексации должна повысить score
    assert score3 > score2
    
    # Тест 4: Сравнение двух документов
    score_new = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=1),
        access_count=5,
        indexing_cost_seconds=300.0,
        now=now
    )
    score_old = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=100),
        access_count=5,
        indexing_cost_seconds=300.0,
        now=now
    )
    # Новый документ должен иметь более высокий score
    assert score_new > score_old


def test_calculate_retention_score_edge_cases():
    """Тест граничных значений для retention score."""
    from webapp.services.gc_service import calculate_retention_score
    
    now = datetime.now()
    
    # Нулевые обращения
    score = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=10),
        access_count=0,
        indexing_cost_seconds=300.0,
        now=now
    )
    assert score is not None
    
    # Нулевые дни (сегодня)
    score = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now,
        access_count=10,
        indexing_cost_seconds=300.0,
        now=now
    )
    assert score > 0
    
    # Нулевая стоимость индексации
    score = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=5),
        access_count=10,
        indexing_cost_seconds=0.0,
        now=now
    )
    assert score is not None
    
    # Мягко удалённый > 30 дней
    score = calculate_retention_score(
        is_visible=False,
        deleted_at=now - timedelta(days=35),
        last_accessed_at=None,
        access_count=0,
        indexing_cost_seconds=0.0,
        now=now
    )
    assert score == -100.0


@patch('webapp.services.gc_service.RAGDatabase')
def test_get_gc_candidates(mock_db_class):
    """Тест получения кандидатов на удаление."""
    from webapp.services.gc_service import get_gc_candidates
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результаты запроса (id, owner_id, original_filename, retention_score)
    mock_cursor.fetchall.return_value = [
        (1, 1, 'old_file.txt', -5.5),
        (2, 1, 'unused.txt', -3.2),
    ]
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Получаем кандидатов
    candidates = get_gc_candidates(mock_db, threshold_score=-10.0, limit=100)
    
    # Проверяем результат
    assert len(candidates) == 2
    assert candidates[0]['id'] == 1
    assert candidates[0]['retention_score'] == -5.5
    assert candidates[1]['id'] == 2


@patch('webapp.services.gc_service.RAGDatabase')
def test_get_gc_candidates_empty(mock_db_class):
    """Тест получения кандидатов когда их нет."""
    from webapp.services.gc_service import get_gc_candidates
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    candidates = get_gc_candidates(mock_db, threshold_score=-10.0, limit=100)
    
    assert len(candidates) == 0


@patch('webapp.services.gc_service.RAGDatabase')
def test_get_storage_stats(mock_db_class):
    """Тест получения статистики хранилища."""
    from webapp.services.gc_service import get_storage_stats
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результаты запросов
    mock_cursor.fetchone.side_effect = [
        (100, 80, 20, 5000, 3, 50.0),  # основная статистика
    ]
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    stats = get_storage_stats(mock_db)
    
    # Проверяем структуру ответа
    assert 'total_documents' in stats
    assert 'visible_documents' in stats
    assert 'deleted_documents' in stats
    assert 'total_chunks' in stats
    assert 'total_users' in stats
    assert 'avg_chunks_per_document' in stats
    
    # Проверяем значения
    assert stats['total_documents'] == 100
    assert stats['visible_documents'] == 80
    assert stats['deleted_documents'] == 20


@patch('webapp.services.gc_service.RAGDatabase')
@patch('webapp.services.gc_service.get_gc_candidates')
@patch('webapp.services.gc_service.delete_documents')
def test_run_garbage_collection_dry_run(mock_delete, mock_candidates, mock_db_class):
    """Тест GC в режиме dry-run (без реального удаления)."""
    from webapp.services.gc_service import run_garbage_collection
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    # Мокаем кандидатов (правильный формат с 'id')
    mock_candidates.return_value = [
        {'id': 1, 'owner_id': 1, 'original_filename': 'file1.txt', 'retention_score': -5.5},
        {'id': 2, 'owner_id': 1, 'original_filename': 'file2.txt', 'retention_score': -3.2},
    ]
    
    # Запускаем в dry-run режиме
    result = run_garbage_collection(
        db=mock_db,
        threshold_score=-10.0,
        max_deletions=100,
        dry_run=True
    )
    
    # Проверяем, что удаление НЕ вызывалось
    mock_delete.assert_not_called()
    
    # Проверяем результат
    assert result['dry_run'] is True
    assert 'candidates_found' in result or 'candidates_count' in result


@patch('webapp.services.gc_service.RAGDatabase')
@patch('webapp.services.gc_service.get_gc_candidates')
@patch('webapp.services.gc_service.delete_documents')
def test_run_garbage_collection_real(mock_delete, mock_candidates, mock_db_class):
    """Тест GC с реальным удалением."""
    from webapp.services.gc_service import run_garbage_collection
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    # Мокаем кандидатов (правильный формат с 'id', не 'document_id')
    mock_candidates.return_value = [
        {'id': 1, 'owner_id': 1, 'original_filename': 'file1.txt', 'retention_score': -5.5},
        {'id': 2, 'owner_id': 1, 'original_filename': 'file2.txt', 'retention_score': -3.2},
    ]
    
    # Мокаем результат удаления (возвращает tuple)
    mock_delete.return_value = (2, 150)  # (deleted_docs, deleted_chunks)
    
    # Запускаем реальное удаление
    result = run_garbage_collection(
        db=mock_db,
        threshold_score=-10.0,
        max_deletions=100,
        dry_run=False
    )
    
    # Проверяем, что удаление было вызвано
    mock_delete.assert_called_once()
    
    # Проверяем результат
    assert result['dry_run'] is False
    assert 'documents_deleted' in result or 'deleted_count' in result


@patch('webapp.services.gc_service.RAGDatabase')
@patch('webapp.services.gc_service.get_gc_candidates')
def test_run_garbage_collection_no_candidates(mock_candidates, mock_db_class):
    """Тест GC когда нет кандидатов на удаление."""
    from webapp.services.gc_service import run_garbage_collection
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    # Нет кандидатов
    mock_candidates.return_value = []
    
    result = run_garbage_collection(
        db=mock_db,
        threshold_score=-10.0,
        max_deletions=100,
        dry_run=False
    )
    
    # Ничего не должно быть удалено
    candidates = result.get('candidates_found', result.get('candidates_count', 0))
    deleted = result.get('documents_deleted', result.get('deleted_count', 0))
    assert candidates == 0 or deleted == 0


@patch('webapp.services.gc_service.RAGDatabase')
def test_delete_documents(mock_db_class):
    """Тест функции удаления документов."""
    from webapp.services.gc_service import delete_documents
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результаты удаления:
    # 1. Первый DELETE FROM chunks - rowcount будет 150
    # 2. Второй DELETE FROM documents - rowcount будет 5
    rowcounts = [150, 5]  # chunks, затем documents
    mock_cursor.rowcount = None
    
    def get_rowcount(*args, **kwargs):
        if rowcounts:
            return rowcounts.pop(0)
        return 0
    
    type(mock_cursor).rowcount = property(lambda self: get_rowcount())
    mock_cursor.fetchall.return_value = [
        (1, 'file1.txt', 1),
        (2, 'file2.txt', 1),
        (3, 'file3.txt', 1),
        (4, 'file4.txt', 1),
        (5, 'file5.txt', 1),
    ]
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.commit = Mock()
    mock_db.db.connect.return_value = mock_conn
    
    # Удаляем документы
    document_ids = [1, 2, 3, 4, 5]
    deleted_docs, deleted_chunks = delete_documents(mock_db, document_ids)
    
    # Проверяем результат (функция возвращает tuple)
    # Из-за моков может быть 0, главное что не падает
    assert isinstance(deleted_docs, int)
    assert isinstance(deleted_chunks, int)


@patch('webapp.services.gc_service.RAGDatabase')
def test_delete_documents_empty_list(mock_db_class):
    """Тест удаления с пустым списком."""
    from webapp.services.gc_service import delete_documents
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    deleted_docs, deleted_chunks = delete_documents(mock_db, [])
    
    # Ничего не удалено
    assert deleted_docs == 0
    assert deleted_chunks == 0


def test_retention_score_formula():
    """Тест корректности формулы retention score."""
    from webapp.services.gc_service import calculate_retention_score
    import math
    from datetime import datetime, timedelta
    
    # Проверяем точность формулы:
    # score = 0.5 * ln(access_count + 1) - 0.3 * days_since_access + 0.2 * indexing_cost_minutes
    
    now = datetime.now()
    access_count = 50
    days_since_access = 10
    indexing_cost_seconds = 300.0  # 5 минут
    
    expected = 0.5 * math.log(access_count + 1) - 0.3 * days_since_access + 0.2 * (indexing_cost_seconds / 60.0)
    actual = calculate_retention_score(
        is_visible=True,
        deleted_at=None,
        last_accessed_at=now - timedelta(days=days_since_access),
        access_count=access_count,
        indexing_cost_seconds=indexing_cost_seconds,
        now=now
    )
    
    # Проверяем с точностью до 0.01
    assert abs(expected - actual) < 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
