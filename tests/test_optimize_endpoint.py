"""
Интеграционный тест для функции оптимизации текста
"""
import pytest
import json


@pytest.fixture
def flask_app():
    """Создаёт тестовое приложение."""
    try:
        from webapp import create_app
        app = create_app('testing')
    except ImportError:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import app as old_app
        app = old_app.app
    return app


@pytest.fixture
def client(flask_app):
    """Создаёт тестовый клиент."""
    return flask_app.test_client()


def test_optimize_preview_endpoint(client):
    """Тест эндпоинта оптимизации"""
    test_text = """=================================
         ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ
=================================
Стр. 1 из 10

Артикул: ТВ-2024-001
Наименование: Телевизор
Диагональ: 55 дюймов

-----------------------------
Стр. 2 из 10
Цена: 45990.00 руб."""
    
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': test_text},
        content_type='application/json'
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    assert data['success'] == True
    assert 'optimized_text' in data
    assert 'change_spans' in data
    assert 'chars_before' in data
    assert 'chars_after' in data
    assert 'reduction_pct' in data
    
    # Проверяем что технические данные сохранились
    assert 'ТВ-2024-001' in data['optimized_text']
    assert 'Телевизор' in data['optimized_text']
    assert '45990.00' in data['optimized_text']
    
    # Проверяем что шум удалён
    assert '=====' not in data['optimized_text']
    assert 'Стр.' not in data['optimized_text'] or data['optimized_text'].count('Стр.') <= 1
    
    # Проверяем экономию
    assert data['chars_after'] < data['chars_before']
    assert data['reduction_pct'] > 10.0


def test_optimize_empty_text(client):
    """Тест оптимизации пустого текста"""
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': ''},
        content_type='application/json'
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] == False
    assert 'Нет текста' in data['message']


def test_optimize_no_changes_needed(client):
    """Тест текста который уже оптимален"""
    test_text = "Простой чистый текст без шума"
    
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': test_text},
        content_type='application/json'
    )
    
    # Может вернуть 200 с минимальными изменениями или сообщение что изменений нет
    data = json.loads(response.data)
    
    if data['success']:
        # Минимальные изменения
        assert data['reduction_pct'] < 5.0
    else:
        # Сообщение что текст оптимален
        assert 'оптимален' in data['message'].lower()


def test_optimize_too_large_text(client):
    """Тест очень большого текста"""
    # Генерируем текст больше 1MB
    large_text = "x" * (1_000_001)
    
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': large_text},
        content_type='application/json'
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] == False
    assert 'слишком большой' in data['message'].lower()


def test_optimize_with_technical_data_preservation(client):
    """Тест сохранения технических данных"""
    test_text = """Документ с техническими данными
Артикул: АБВ-123
Дата: 31.10.2025
ГОСТ 12345-67
Размер: 100x200 мм
Цена: 1500.50 руб.

===================
Стр. 1 из 5
===================
"""
    
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': test_text},
        content_type='application/json'
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] == True
    
    optimized = data['optimized_text']
    
    # Все технические данные должны сохраниться
    assert 'АБВ-123' in optimized
    assert '31.10.2025' in optimized
    assert 'ГОСТ 12345-67' in optimized
    assert '100x200' in optimized
    assert '1500.50' in optimized
    
    # Декоративные линии должны быть удалены
    assert '=========' not in optimized


def test_optimize_change_spans_format(client):
    """Тест формата change_spans"""
    test_text = """Заголовок
==================
Текст
"""
    
    response = client.post(
        '/ai_analysis/optimize/preview',
        json={'text': test_text},
        content_type='application/json'
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Проверяем структуру change_spans
    if data['change_spans']:
        for span in data['change_spans']:
            assert 'start' in span
            assert 'end' in span
            assert 'reason' in span
            assert isinstance(span['start'], int)
            assert isinstance(span['end'], int)
            assert isinstance(span['reason'], str)
            assert span['end'] > span['start']
