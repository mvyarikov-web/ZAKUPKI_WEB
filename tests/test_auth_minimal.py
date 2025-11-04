"""Минимальный тест для отладки auth flow."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from webapp import create_app
from webapp.db.base import Base


@pytest.fixture(scope='function')
def test_app():
    """Создаёт изолированное приложение с отдельной БД для каждого теста."""
    # Создаём отдельный engine
    test_engine = create_engine(
        'sqlite:///:memory:',
        echo=True,  # Включаем SQL logging
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    
    # Создаём таблицы
    Base.metadata.create_all(bind=test_engine)
    
    # Создаём фабрику сессий для тестов
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Подменяем глобальную фабрику
    import webapp.db.base
    original_session_local = webapp.db.base.SessionLocal
    webapp.db.base.SessionLocal = TestSessionLocal
    
    app = create_app('testing')
    app.config['TESTING'] = True
    
    yield app
    
    # Восстанавливаем
    webapp.db.base.SessionLocal = original_session_local
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_register_then_login(test_app):
    """Тест: регистрация → логин."""
    client = test_app.test_client()
    
    # 1. Регистрация
    print("\n=== REGISTER ===")
    reg_response = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'password123',
        'role': 'user'
    })
    print(f"Status: {reg_response.status_code}")
    print(f"Data: {reg_response.get_json()}")
    assert reg_response.status_code == 201
    
    # 2. Логин
    print("\n=== LOGIN ===")
    login_response = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'password123'
    })
    print(f"Status: {login_response.status_code}")
    print(f"Data: {login_response.get_json()}")
    assert login_response.status_code == 200
    assert 'token' in login_response.get_json()
