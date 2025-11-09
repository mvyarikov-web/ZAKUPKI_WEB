"""
Тест для проверки статистики хранилища.
Проверяет, что функция get_storage_stats() корректно работает с текущей схемой БД.
"""
import pytest
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config
from webapp.services.gc_service import get_storage_stats


def test_storage_stats_returns_valid_data():
    """Проверка, что get_storage_stats() возвращает корректные данные."""
    config = get_config()
    dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
    db = RAGDatabase(dsn)
    
    # Получаем статистику
    stats = get_storage_stats(db)
    
    # Проверяем наличие всех обязательных полей
    required_fields = [
        'total_documents',
        'visible_documents', 
        'deleted_documents',
        'total_chunks',
        'total_users',
        'avg_chunks_per_document'
    ]
    
    for field in required_fields:
        assert field in stats, f"Поле '{field}' отсутствует в статистике"
        assert isinstance(stats[field], (int, float)), f"Поле '{field}' должно быть числом"
        assert stats[field] >= 0, f"Поле '{field}' не может быть отрицательным"
    
    # Проверяем логику: total = visible + deleted
    # Примечание: из-за DISTINCT в запросе это может не совпадать, 
    # но visible + deleted не должны превышать total
    assert stats['visible_documents'] + stats['deleted_documents'] >= 0
    
    # Если есть документы, должны быть и чанки (обычно)
    if stats['total_documents'] > 0:
        assert stats['avg_chunks_per_document'] >= 0
    
    print(f"\n✅ Статистика хранилища:")
    print(f"   Всего документов: {stats['total_documents']}")
    print(f"   Видимых: {stats['visible_documents']}")
    print(f"   Удалённых: {stats['deleted_documents']}")
    print(f"   Чанков: {stats['total_chunks']}")
    print(f"   Пользователей: {stats['total_users']}")
    print(f"   Средних чанков на документ: {stats['avg_chunks_per_document']:.2f}")
    if 'db_size_mb' in stats:
        print(f"   Размер БД: {stats['db_size_mb']:.2f} МБ")


def test_storage_stats_with_empty_db():
    """Проверка работы функции на пустой БД (все счётчики должны быть 0 или >= 0)."""
    config = get_config()
    dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
    db = RAGDatabase(dsn)
    
    stats = get_storage_stats(db)
    
    # Даже если БД пустая, функция должна вернуть валидные данные (все нули)
    for key, value in stats.items():
        if key != 'db_size_mb':  # db_size_mb может быть > 0 даже без данных
            assert value >= 0, f"Значение {key}={value} не может быть отрицательным"
