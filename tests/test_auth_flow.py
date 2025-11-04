"""
Интеграционные тесты для authentication flow.

Проверяет полный цикл аутентификации:
- Регистрация пользователя
- Логин с получением JWT токена
- Доступ к защищённым эндпоинтам
- Логаут и инвалидация токена
- Смена пароля
"""

import pytest
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from webapp import create_app
from webapp.db.base import Base, get_db_session
from webapp.db.models import User, Session as SessionModel
from webapp.db.repositories import UserRepository, SessionRepository


@pytest.fixture(scope='function', autouse=True)
def setup_test_database():
    """
    Настраивает изолированную БД для каждого теста.
    Подменяет глобальный SessionLocal на тестовую фабрику с отдельным in-memory SQLite.
    """
    # Создаём отдельный engine для каждого теста (полная изоляция)
    test_engine = create_engine(
        'sqlite:///:memory:',
        echo=False,
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    
    # Создаём таблицы
    Base.metadata.create_all(bind=test_engine)
    
    # Создаём фабрику сессий для тестов
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Подменяем глобальную фабрику сессий на тестовую
    import webapp.db.base
    original_session_local = webapp.db.base.SessionLocal
    webapp.db.base.SessionLocal = TestSessionLocal
    
    yield test_engine
    
    # Восстанавливаем оригинальную фабрику
    webapp.db.base.SessionLocal = original_session_local
    
    # Очищаем таблицы и закрываем engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope='function')
def app(setup_test_database):
    """Создаёт Flask приложение для тестирования."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['JWT_EXPIRATION_HOURS'] = 1  # Короткое время для тестов
    
    yield app


@pytest.fixture
def client(app):
    """Создаёт тестовый клиент."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Создаёт сессию БД для тестов (использует тот же тестовый engine)."""
    import webapp.db.base
    session = webapp.db.base.SessionLocal()
    yield session
    session.close()


def test_register_user(client):
    """Тест регистрации нового пользователя."""
    response = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123',
        'role': 'user'
    })
    
    if response.status_code != 201:
        print(f"\n❌ Ошибка регистрации: {response.get_json()}")
    
    assert response.status_code == 201
    data = response.get_json()
    assert data['success'] is True
    assert data['user']['email'] == 'test@example.com'
    assert data['user']['role'] == 'user'
    assert 'id' in data['user']


def test_register_duplicate_email(client):
    """Тест регистрации с дублирующимся email."""
    # Первая регистрация
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    # Попытка второй регистрации с тем же email
    response = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'another_password'
    })
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'уже существует' in data['error'].lower()


def test_register_invalid_email(client):
    """Тест регистрации с некорректным email."""
    response = client.post('/auth/register', json={
        'email': 'invalid_email',
        'password': 'password123'
    })
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'email' in data['error'].lower()


def test_register_short_password(client):
    """Тест регистрации со слишком коротким паролем."""
    response = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': '123'  # Меньше 6 символов
    })
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'пароль' in data['error'].lower()


def test_login_success(client):
    """Тест успешного входа."""
    # Сначала регистрируем пользователя
    reg_response = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    print(f"\n📋 Registration: {reg_response.status_code} - {reg_response.get_json()}")
    
    # Входим
    response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    print(f"\n📋 Login: {response.status_code} - {response.get_json()}")
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'token' in data
    assert len(data['token']) > 0
    assert data['user']['email'] == 'test@example.com'


def test_login_wrong_password(client):
    """Тест входа с неверным паролем."""
    # Регистрация
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    # Вход с неверным паролем
    response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'wrong_password'
    })
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'неверный' in data['error'].lower()


def test_login_nonexistent_user(client):
    """Тест входа несуществующего пользователя."""
    response = client.post('/auth/login', json={
        'email': 'nonexistent@example.com',
        'password': 'password123'
    })
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False


def test_access_protected_endpoint(client):
    """Тест доступа к защищённому эндпоинту."""
    # Регистрация и вход
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    login_response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    token = login_response.get_json()['token']
    
    # Доступ к защищённому эндпоинту /auth/me
    response = client.get('/auth/me', headers={
        'Authorization': f'Bearer {token}'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['user']['email'] == 'test@example.com'


def test_access_protected_without_token(client):
    """Тест доступа к защищённому эндпоинту без токена."""
    response = client.get('/auth/me')
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False


def test_logout(client):
    """Тест выхода пользователя."""
    # Регистрация и вход
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    login_response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    token = login_response.get_json()['token']
    
    # Выход
    response = client.post('/auth/logout', headers={
        'Authorization': f'Bearer {token}'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    
    # Попытка использовать токен после выхода
    response_after_logout = client.get('/auth/me', headers={
        'Authorization': f'Bearer {token}'
    })
    
    assert response_after_logout.status_code == 401


def test_change_password(client):
    """Тест смены пароля."""
    # Регистрация и вход
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'old_password'
    })
    
    login_response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'old_password'
    })
    old_token = login_response.get_json()['token']
    
    # Смена пароля
    response = client.post('/auth/change-password', 
        json={
            'old_password': 'old_password',
            'new_password': 'new_password'
        },
        headers={'Authorization': f'Bearer {old_token}'}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    
    # Старый токен больше не работает
    response_old_token = client.get('/auth/me', headers={
        'Authorization': f'Bearer {old_token}'
    })
    assert response_old_token.status_code == 401
    
    # Вход с новым паролем
    new_login_response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'new_password'
    })
    
    assert new_login_response.status_code == 200
    assert 'token' in new_login_response.get_json()


def test_session_created_in_db(client, db_session):
    """Тест создания сессии в БД при логине."""
    # Регистрация и вход
    client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    
    # Проверяем, что сессия создана в БД
    session_repo = SessionRepository(db_session)
    
    # Получаем пользователя
    user_repo = UserRepository(db_session)
    user = user_repo.get_by_email('test@example.com')
    
    # Проверяем сессии пользователя
    sessions = session_repo.get_user_sessions(user.id, active_only=True)
    
    assert len(sessions) == 1
    assert sessions[0].is_active is True
    assert sessions[0].expires_at > datetime.utcnow()


def test_full_auth_flow(client):
    """
    Полный интеграционный тест: регистрация → логин → доступ → логаут.
    """
    # 1. Регистрация
    register_response = client.post('/auth/register', json={
        'email': 'fulltest@example.com',
        'password': 'test_password'
    })
    assert register_response.status_code == 201
    
    # 2. Логин
    login_response = client.post('/auth/login', json={
        'email': 'fulltest@example.com',
        'password': 'test_password'
    })
    assert login_response.status_code == 200
    token = login_response.get_json()['token']
    
    # 3. Доступ к защищённому эндпоинту
    me_response = client.get('/auth/me', headers={
        'Authorization': f'Bearer {token}'
    })
    assert me_response.status_code == 200
    assert me_response.get_json()['user']['email'] == 'fulltest@example.com'
    
    # 4. Логаут
    logout_response = client.post('/auth/logout', headers={
        'Authorization': f'Bearer {token}'
    })
    assert logout_response.status_code == 200
    
    # 5. Проверка, что токен больше не работает
    me_after_logout = client.get('/auth/me', headers={
        'Authorization': f'Bearer {token}'
    })
    assert me_after_logout.status_code == 401
