"""Тесты для эндпоинта /clear_all (increment-002)."""
import os
import pytest
from webapp import create_app


@pytest.fixture
def app():
    """Создаёт тестовое приложение."""
    app = create_app('testing')
    yield app


@pytest.fixture
def client(app):
    """Создаёт тестовый клиент."""
    return app.test_client()


def test_clear_all_empty_folders(client, app, tmp_path):
    """Тест очистки при пустых папках."""
    # Переопределяем пути на временные
    app.config['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    app.config['INDEX_FOLDER'] = str(tmp_path / 'index')
    app.config['SEARCH_RESULTS_FILE'] = str(tmp_path / 'index' / 'search_results.json')
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['INDEX_FOLDER'], exist_ok=True)
    
    response = client.post('/clear_all')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] is True
    assert data['deleted_count'] == 0
    assert data['index_deleted'] is False
    assert data['errors'] == []


def test_clear_all_with_files(client, app, tmp_path):
    """Тест очистки с файлами и индексом."""
    # Переопределяем пути на временные
    app.config['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    app.config['INDEX_FOLDER'] = str(tmp_path / 'index')
    app.config['SEARCH_RESULTS_FILE'] = str(tmp_path / 'index' / 'search_results.json')
    
    uploads = tmp_path / 'uploads'
    index_folder = tmp_path / 'index'
    uploads.mkdir()
    index_folder.mkdir()
    
    # Создаём тестовые файлы
    (uploads / 'test.txt').write_text('test content')
    test_folder = uploads / 'test_folder'
    test_folder.mkdir()
    (test_folder / 'file.txt').write_text('folder content')
    
    # Создаём индекс
    index_file = index_folder / '_search_index.txt'
    index_file.write_text('test index')
    
    response = client.post('/clear_all')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] is True
    assert data['deleted_count'] == 2  # файл + папка
    assert data['index_deleted'] is True
    assert data['errors'] == []
    
    # Проверяем, что файлы удалены
    assert not (uploads / 'test.txt').exists()
    assert not test_folder.exists()
    assert not index_file.exists()
    
    # Папки остаются
    assert uploads.exists()
    assert index_folder.exists()
