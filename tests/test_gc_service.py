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
    
    # Тест 1: Недавно используемый документ с высокой активностью
    score1 = calculate_retention_score(
        access_count=100,
        days_since_access=1,
        indexing_cost_minutes=10
    )
    # Должен быть высокий положительный score
    assert score1 > 0
    
    # Тест 2: Старый неиспользуемый документ
    score2 = calculate_retention_score(
        access_count=0,
        days_since_access=365,
        indexing_cost_minutes=1
    )
    # Должен быть отрицательный score
    assert score2 < 0
    
    # Тест 3: Документ с высокой стоимостью индексации
    score3 = calculate_retention_score(
        access_count=10,
        days_since_access=30,
        indexing_cost_minutes=100
    )
    # Высокая стоимость индексации должна повысить score
    assert score3 > score2
    
    # Тест 4: Сравнение двух документов
    score_new = calculate_retention_score(
        access_count=5,
        days_since_access=1,
        indexing_cost_minutes=5
    )
    score_old = calculate_retention_score(
        access_count=5,
        days_since_access=100,
        indexing_cost_minutes=5
    )
    # Новый документ должен иметь более высокий score
    assert score_new > score_old


def test_calculate_retention_score_edge_cases():
    """Тест граничных значений для retention score."""
    from webapp.services.gc_service import calculate_retention_score
    
    # Нулевые обращения
    score = calculate_retention_score(0, 10, 5)
    assert score is not None
    
    # Нулевые дни (сегодня)
    score = calculate_retention_score(10, 0, 5)
    assert score > 0
    
    # Нулевая стоимость индексации
    score = calculate_retention_score(10, 5, 0)
    assert score is not None


@patch('webapp.services.gc_service.RAGDatabase')
def test_get_gc_candidates(mock_db_class):
    """Тест получения кандидатов на удаление."""
    from webapp.services.gc_service import get_gc_candidates
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результаты запроса
    mock_cursor.fetchall.return_value = [
        (1, 1, 'old_file.txt', '/path/old', -5.5, 0, datetime.now() - timedelta(days=100), 10),
        (2, 1, 'unused.txt', '/path/unused', -3.2, 1, datetime.now() - timedelta(days=50), 5),
    ]
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Получаем кандидатов
    candidates = get_gc_candidates(mock_db, threshold=-10.0, limit=100)
    
    # Проверяем результат
    assert len(candidates) == 2
    assert candidates[0]['document_id'] == 1
    assert candidates[0]['retention_score'] == -5.5
    assert candidates[1]['document_id'] == 2


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
    
    candidates = get_gc_candidates(mock_db, threshold=-10.0, limit=100)
    
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
    
    # Мокаем кандидатов
    mock_candidates.return_value = [
        {'document_id': 1, 'retention_score': -5.5},
        {'document_id': 2, 'retention_score': -3.2},
    ]
    
    # Запускаем в dry-run режиме
    result = run_garbage_collection(
        db=mock_db,
        threshold=-10.0,
        batch_size=100,
        dry_run=True
    )
    
    # Проверяем, что удаление НЕ вызывалось
    mock_delete.assert_not_called()
    
    # Проверяем результат
    assert result['dry_run'] is True
    assert result['candidates_found'] == 2
    assert result['deleted_count'] == 0


@patch('webapp.services.gc_service.RAGDatabase')
@patch('webapp.services.gc_service.get_gc_candidates')
@patch('webapp.services.gc_service.delete_documents')
def test_run_garbage_collection_real(mock_delete, mock_candidates, mock_db_class):
    """Тест GC с реальным удалением."""
    from webapp.services.gc_service import run_garbage_collection
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    # Мокаем кандидатов
    mock_candidates.return_value = [
        {'document_id': 1, 'retention_score': -5.5},
        {'document_id': 2, 'retention_score': -3.2},
    ]
    
    # Мокаем результат удаления
    mock_delete.return_value = {
        'deleted_documents': 2,
        'deleted_chunks': 150,
        'freed_space_bytes': 2048000
    }
    
    # Запускаем реальное удаление
    result = run_garbage_collection(
        db=mock_db,
        threshold=-10.0,
        batch_size=100,
        dry_run=False
    )
    
    # Проверяем, что удаление было вызвано
    mock_delete.assert_called_once()
    
    # Проверяем результат
    assert result['dry_run'] is False
    assert result['candidates_found'] == 2
    assert result['deleted_count'] == 2
    assert result['deleted_chunks'] == 150
    assert result['freed_space_bytes'] == 2048000


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
        threshold=-10.0,
        batch_size=100,
        dry_run=False
    )
    
    # Ничего не должно быть удалено
    assert result['candidates_found'] == 0
    assert result['deleted_count'] == 0


@patch('webapp.services.gc_service.RAGDatabase')
def test_delete_documents(mock_db_class):
    """Тест функции удаления документов."""
    from webapp.services.gc_service import delete_documents
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результаты удаления
    mock_cursor.rowcount = 5  # удалено 5 документов
    mock_cursor.fetchone.side_effect = [
        (150,),  # удалено чанков
        (2048000,)  # освобождено байт
    ]
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Удаляем документы
    document_ids = [1, 2, 3, 4, 5]
    result = delete_documents(mock_db, document_ids)
    
    # Проверяем результат
    assert result['deleted_documents'] == 5
    assert result['deleted_chunks'] == 150
    assert result['freed_space_bytes'] == 2048000


@patch('webapp.services.gc_service.RAGDatabase')
def test_delete_documents_empty_list(mock_db_class):
    """Тест удаления с пустым списком."""
    from webapp.services.gc_service import delete_documents
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    result = delete_documents(mock_db, [])
    
    # Ничего не удалено
    assert result['deleted_documents'] == 0
    assert result['deleted_chunks'] == 0
    assert result['freed_space_bytes'] == 0


def test_retention_score_formula():
    """Тест корректности формулы retention score."""
    from webapp.services.gc_service import calculate_retention_score
    import math
    
    # Проверяем точность формулы:
    # score = 0.5 * ln(access_count + 1) - 0.3 * days_since_access + 0.2 * indexing_cost_minutes
    
    access_count = 50
    days_since_access = 10
    indexing_cost_minutes = 5
    
    expected = 0.5 * math.log(access_count + 1) - 0.3 * days_since_access + 0.2 * indexing_cost_minutes
    actual = calculate_retention_score(access_count, days_since_access, indexing_cost_minutes)
    
    # Проверяем с точностью до 0.01
    assert abs(expected - actual) < 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
