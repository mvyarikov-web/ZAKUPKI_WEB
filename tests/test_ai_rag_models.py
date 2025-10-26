"""Тесты для загрузки и управления моделями AI RAG."""
import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp import create_app


@pytest.fixture
def app():
    """Создание тестового приложения."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def app_with_models_config(app):
    """Приложение с временным файлом конфигурации моделей."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        tmp_path = tmp.name
    
    app.config['RAG_MODELS_FILE'] = tmp_path
    
    yield app
    
    # Очистка
    try:
        os.unlink(tmp_path)
    except:
        pass


def test_get_models_endpoint_returns_valid_json(app_with_models_config):
    """GET /ai_rag/models должен возвращать валидный JSON с моделями."""
    client = app_with_models_config.test_client()
    
    # Создаём минимальную конфигурацию
    models_file = app_with_models_config.config['RAG_MODELS_FILE']
    config = {
        'models': [
            {
                'model_id': 'gpt-4o-mini',
                'display_name': 'GPT-4o Mini',
                'context_window_tokens': 128000,
                'price_input_per_1m': 0.15,
                'price_output_per_1m': 0.60,
                'enabled': True
            }
        ],
        'default_model': 'gpt-4o-mini'
    }
    
    with open(models_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    # Запрос к эндпоинту
    response = client.get('/ai_rag/models')
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data is not None, "Response должен быть JSON"
    assert data.get('success') is True, f"Expected success=True, got {data}"
    assert 'models' in data, "Response должен содержать 'models'"
    assert 'default_model' in data, "Response должен содержать 'default_model'"
    assert isinstance(data['models'], list), "'models' должен быть списком"
    assert len(data['models']) > 0, "Должна быть хотя бы одна модель"
    
    model = data['models'][0]
    assert 'model_id' in model
    assert 'display_name' in model
    assert 'price_input_per_1m' in model
    assert 'price_output_per_1m' in model


def test_models_migration_from_array_format(app_with_models_config):
    """Миграция старого формата (массив) в новый формат (объект с models и default_model)."""
    client = app_with_models_config.test_client()
    models_file = app_with_models_config.config['RAG_MODELS_FILE']
    
    # Старый формат: просто массив моделей
    old_format = [
        {
            'model_id': 'gpt-4-turbo',
            'display_name': 'GPT-4 Turbo',
            'context_window_tokens': 128000,
            'price_input_per_1M': 10.0,  # Старый ключ с заглавной M
            'price_output_per_1M': 30.0,
            'enabled': True
        }
    ]
    
    with open(models_file, 'w', encoding='utf-8') as f:
        json.dump(old_format, f)
    
    # Запрос должен вызвать миграцию
    response = client.get('/ai_rag/models')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert len(data['models']) == 1
    
    model = data['models'][0]
    # Проверяем, что старые ключи мигрированы
    assert 'price_input_per_1m' in model
    assert model['price_input_per_1m'] == 10.0
    assert model['price_output_per_1m'] == 30.0
    
    # Проверяем, что файл был сохранён в новом формате
    with open(models_file, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    
    assert isinstance(saved, dict), "После миграции должен быть объект, а не массив"
    assert 'models' in saved
    assert 'default_model' in saved
    assert saved['default_model'] == 'gpt-4-turbo'


def test_models_endpoint_handles_missing_file(app_with_models_config):
    """Если models.json отсутствует, должна вернуться дефолтная конфигурация."""
    client = app_with_models_config.test_client()
    models_file = app_with_models_config.config['RAG_MODELS_FILE']
    
    # Удаляем файл если существует
    if os.path.exists(models_file):
        os.unlink(models_file)
    
    response = client.get('/ai_rag/models')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert len(data['models']) > 0, "Должна быть дефолтная модель"
    assert data['default_model'] is not None


def test_models_endpoint_handles_corrupted_json(app_with_models_config):
    """Если models.json повреждён, должна вернуться дефолтная конфигурация."""
    client = app_with_models_config.test_client()
    models_file = app_with_models_config.config['RAG_MODELS_FILE']
    
    # Пишем невалидный JSON
    with open(models_file, 'w', encoding='utf-8') as f:
        f.write('{ invalid json content }')
    
    response = client.get('/ai_rag/models')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert len(data['models']) > 0, "Должна быть дефолтная модель при ошибке"


def test_update_model_prices(app_with_models_config):
    """POST /ai_rag/models должен обновлять цены модели."""
    client = app_with_models_config.test_client()
    models_file = app_with_models_config.config['RAG_MODELS_FILE']
    
    # Создаём начальную конфигурацию
    config = {
        'models': [
            {
                'model_id': 'test-model',
                'display_name': 'Test Model',
                'context_window_tokens': 4096,
                'price_input_per_1m': 0.0,
                'price_output_per_1m': 0.0,
                'enabled': True
            }
        ],
        'default_model': 'test-model'
    }
    
    with open(models_file, 'w', encoding='utf-8') as f:
        json.dump(config, f)
    
    # Обновляем цены
    response = client.post('/ai_rag/models', json={
        'model_id': 'test-model',
        'price_input_per_1m': 5.0,
        'price_output_per_1m': 15.0
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    
    # Проверяем, что цены сохранились
    response = client.get('/ai_rag/models')
    data = response.get_json()
    model = data['models'][0]
    assert model['price_input_per_1m'] == 5.0
    assert model['price_output_per_1m'] == 15.0
