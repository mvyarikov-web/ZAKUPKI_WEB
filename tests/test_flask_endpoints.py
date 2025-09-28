import os
from typing import Iterator


def test_health_status():
    from app import app as flask_app
    with flask_app.test_client() as client:
        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert data.get('status') == 'ok'


def test_index_status_no_index(tmp_path):
    """Проверяет, что при отсутствии индекса эндпоинт корректно сообщает exists=False."""
    from app import app as flask_app

    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    try:
        # Используем изолированную временную папку для uploads
        uploads_dir = tmp_path / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)

        # Убедимся, что индекс не существует
        idx_path = os.path.join(str(uploads_dir), '_search_index.txt')
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
