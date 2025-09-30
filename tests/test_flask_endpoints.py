import os
from typing import Iterator
import pytest


@pytest.fixture
def flask_app():
    """Создаёт тестовое приложение."""
    try:
        # Пытаемся использовать новую структуру
        from webapp import create_app
        app = create_app('testing')
    except ImportError:
        # Фолбэк на старую структуру если новая еще не применена
        import app as old_app
        app = old_app.app
    return app


def test_health_status(flask_app):
    with flask_app.test_client() as client:
        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert data.get('status') == 'ok'


def test_index_status_no_index(tmp_path, flask_app):
    """Проверяет, что при отсутствии индекса эндпоинт корректно сообщает exists=False."""
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_index = flask_app.config.get('INDEX_FOLDER')
    
    try:
        # Используем изолированную временную папку для uploads и index
        uploads_dir = tmp_path / 'uploads'
        index_dir = tmp_path / 'index'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        index_dir.mkdir(parents=True, exist_ok=True)
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        flask_app.config['INDEX_FOLDER'] = str(index_dir)

        # Убедимся, что индекс не существует
        idx_path = os.path.join(str(index_dir), '_search_index.txt')
        if os.path.exists(idx_path):
            os.remove(idx_path)

        with flask_app.test_client() as client:
            resp = client.get('/index_status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert isinstance(data, dict)
            assert data.get('exists') is False
    finally:
        # Восстановим исходную конфигурацию
        flask_app.config['UPLOAD_FOLDER'] = old_upload
        flask_app.config['INDEX_FOLDER'] = old_index
