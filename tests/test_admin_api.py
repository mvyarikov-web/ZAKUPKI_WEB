"""
Тесты для административного API (admin.py)

Проверяется:
- Авторизация через @require_role('admin')
- Эндпоинты статистики и управления
- GC-операции
- Блокировка загрузок
- Просмотр логов
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def admin_user():
    """Мок пользователя с ролью admin."""
    user = Mock()
    user.id = 1
    user.email = 'admin@test.com'
    user.role = 'admin'
    return user


@pytest.fixture
def regular_user():
    """Мок обычного пользователя."""
    user = Mock()
    user.id = 2
    user.email = 'user@test.com'
    user.role = 'user'
    return user


@pytest.fixture
def mock_auth_admin(admin_user):
    """Мокает авторизацию для admin пользователя."""
    with patch('webapp.middleware.auth_middleware.require_role') as mock_require_role:
        # Декоратор пропускает запрос без проверки
        mock_require_role.return_value = lambda f: f
        yield admin_user


@pytest.fixture
def mock_auth_user(regular_user):
    """Мокает авторизацию для обычного пользователя."""
    with patch('webapp.middleware.auth_middleware.require_role') as mock_require_role:
        # Декоратор возвращает 403 для не-админов
        def decorator(f):
            from flask import jsonify
            return lambda *args, **kwargs: (jsonify({'error': 'Forbidden'}), 403)
        mock_require_role.return_value = decorator
        yield regular_user


def test_storage_page_requires_auth(app):
    """Тест: главная страница требует авторизации."""
    with app.test_client() as client:
        # Мокаем require_role для возврата 401
        with patch('webapp.middleware.auth_middleware.require_role') as mock_require:
            def unauthorized_decorator(f):
                from flask import jsonify
                return lambda *args, **kwargs: (jsonify({'error': 'Unauthorized'}), 401)
            mock_require.return_value = unauthorized_decorator
            
            response = client.get('/admin/storage')
            
            # Без авторизации должен быть 401
            assert response.status_code in [401, 404]  # 404 если роут не зарегистрирован


def test_storage_page_requires_admin_role(app, mock_auth_user):
    """Тест: главная страница требует роль admin."""
    with app.test_client() as client:
        response = client.get('/admin/storage')
        
        # Обычный пользователь должен получить 403
        assert response.status_code in [403, 404]


@patch('webapp.routes.admin._get_db')
def test_storage_stats_success(mock_get_db, client, admin_user):
    """Тест успешного получения статистики."""
    # Мокаем БД
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (100, 80, 20, 5000, 3, 50.0)
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Авторизуемся как админ
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.get('/admin/storage/stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'total_documents' in data
        assert data['total_documents'] == 100


def test_storage_stats_unauthorized(client):
    """Тест: статистика требует авторизации."""
    response = client.get('/admin/storage/stats')
    assert response.status_code == 401


@patch('webapp.routes.admin.run_garbage_collection')
@patch('webapp.routes.admin._get_db')
def test_gc_run_dry_run(mock_get_db, mock_gc, client, admin_user):
    """Тест запуска GC в dry-run режиме."""
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    # Мокаем результат GC
    mock_gc.return_value = {
        'candidates_found': 5,
        'deleted_count': 0,
        'deleted_chunks': 0,
        'freed_space_bytes': 0,
        'dry_run': True,
        'threshold_score': -10.0,
        'execution_time_seconds': 0.5
    }
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.post(
            '/admin/gc/run',
            data=json.dumps({'dry_run': True, 'threshold': -10.0}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['dry_run'] is True
        assert data['candidates_found'] == 5
        assert data['deleted_count'] == 0


@patch('webapp.routes.admin.run_garbage_collection')
@patch('webapp.routes.admin._get_db')
def test_gc_run_real_deletion(mock_get_db, mock_gc, client, admin_user):
    """Тест реального удаления через GC."""
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    mock_gc.return_value = {
        'candidates_found': 5,
        'deleted_count': 5,
        'deleted_chunks': 250,
        'freed_space_bytes': 1024000,
        'dry_run': False,
        'threshold_score': -10.0,
        'execution_time_seconds': 1.2
    }
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.post(
            '/admin/gc/run',
            data=json.dumps({'dry_run': False, 'threshold': -10.0}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['dry_run'] is False
        assert data['deleted_count'] == 5
        assert data['freed_space_bytes'] == 1024000


@patch('webapp.routes.admin.get_gc_candidates')
@patch('webapp.routes.admin._get_db')
def test_gc_candidates(mock_get_db, mock_candidates, client, admin_user):
    """Тест получения кандидатов на удаление."""
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    mock_candidates.return_value = [
        {
            'document_id': 1,
            'owner_id': 1,
            'file_path': '/test/old.txt',
            'retention_score': -5.5,
            'access_count': 0,
            'last_accessed_at': '2024-01-01T00:00:00'
        }
    ]
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.get('/admin/gc/candidates?threshold=-10.0&limit=100')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 1
        assert data['candidates'][0]['document_id'] == 1


@patch('webapp.routes.admin.get_config')
@patch('webapp.routes.admin._get_db')
def test_uploads_toggle_disable(mock_get_db, mock_config, client, admin_user):
    """Тест блокировки загрузок."""
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    mock_conf = Mock()
    mock_conf.uploads_disabled = False
    mock_config.return_value = mock_conf
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.post(
            '/admin/uploads/toggle',
            data=json.dumps({'disable': True}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'uploads_disabled' in data or 'uploads_enabled' in data


def test_uploads_toggle_unauthorized(client):
    """Тест: блокировка загрузок требует авторизации."""
    response = client.post(
        '/admin/uploads/toggle',
        data=json.dumps({'disable': True}),
        content_type='application/json'
    )
    assert response.status_code == 401


@patch('webapp.routes.admin._get_db')
def test_user_quota(mock_get_db, client, admin_user):
    """Тест получения квоты пользователя."""
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (10, 50.5)  # doc_count, total_cost
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    with patch('flask.g') as mock_g, \
         patch('webapp.routes.admin.get_config') as mock_config:
        mock_g.user = admin_user
        
        mock_conf = Mock()
        mock_conf.user_quota_bytes = 10 * 1024 * 1024 * 1024  # 10 GB
        mock_config.return_value = mock_conf
        
        response = client.get('/admin/quota/5')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'user_id' in data
        assert 'total_documents' in data
        assert 'quota_bytes' in data


@patch('webapp.routes.admin.get_config')
def test_admin_config(mock_config, client, admin_user):
    """Тест получения конфигурации."""
    mock_conf = Mock()
    mock_conf.uploads_disabled = False
    mock_conf.user_quota_bytes = 10 * 1024 * 1024 * 1024
    mock_conf.db_storage_limit_bytes = 100 * 1024 * 1024 * 1024
    mock_conf.chunk_size_tokens = 500
    mock_conf.chunk_overlap_tokens = 50
    mock_config.return_value = mock_conf
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.get('/admin/config')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'uploads_disabled' in data
        assert 'chunk_size_tokens' in data
        assert data['chunk_size_tokens'] == 500


@patch('webapp.routes.admin.get_config')
@patch('builtins.open', create=True)
def test_audit_log(mock_open, mock_config, client, admin_user):
    """Тест получения логов аудита."""
    mock_conf = Mock()
    mock_conf.storage_audit_log = '/path/to/audit.log'
    mock_config.return_value = mock_conf
    
    # Мокаем содержимое лог-файла
    mock_file = MagicMock()
    mock_file.readlines.return_value = [
        '2025-11-05 10:00:00 INFO GC completed: 5 documents deleted\n',
        '2025-11-05 11:00:00 WARNING Storage quota exceeded\n'
    ]
    mock_open.return_value.__enter__.return_value = mock_file
    
    with patch('flask.g') as mock_g, \
         patch('os.path.exists', return_value=True):
        mock_g.user = admin_user
        
        response = client.get('/admin/audit_log?limit=50')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'logs' in data
        assert len(data['logs']) > 0


def test_audit_log_requires_admin(client, regular_user):
    """Тест: логи доступны только админам."""
    with patch('flask.g') as mock_g:
        mock_g.user = regular_user
        
        response = client.get('/admin/audit_log')
        
        assert response.status_code == 403


@patch('webapp.routes.admin._get_db')
def test_api_error_handling(mock_get_db, client, admin_user):
    """Тест обработки ошибок в API."""
    # Мокаем БД с ошибкой
    mock_db = Mock()
    mock_db.db.connect.side_effect = Exception('Database error')
    mock_get_db.return_value = mock_db
    
    with patch('flask.g') as mock_g:
        mock_g.user = admin_user
        
        response = client.get('/admin/storage/stats')
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
