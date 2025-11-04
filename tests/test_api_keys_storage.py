"""
Тесты для ApiKeyRepository и ApiKeyService.

Проверяет шифрование/расшифровку ключей и CRUD операции в БД.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from webapp.db.base import Base
from webapp.db.repositories import ApiKeyRepository
from webapp.services.api_key_service import ApiKeyService


@pytest.fixture(scope='function')
def test_db_session():
    """Создаёт изолированную тестовую БД в памяти."""
    # Создаём отдельный engine
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
    
    session = TestSessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def api_key_service():
    """Создаёт ApiKeyService с тестовым ключом."""
    # Генерируем тестовый ключ Fernet
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key()
    return ApiKeyService(test_key)


def test_encrypt_decrypt_key(api_key_service):
    """Тест шифрования и расшифровки ключа."""
    plain_key = "sk-proj-test123abc456"
    
    # Шифрование
    encrypted = api_key_service.encrypt_key(plain_key)
    assert encrypted != plain_key
    assert len(encrypted) > len(plain_key)
    
    # Расшифровка
    decrypted = api_key_service.decrypt_key(encrypted)
    assert decrypted == plain_key


def test_mask_key():
    """Тест маскирования ключа."""
    key = "sk-proj-abc123def456"
    
    masked = ApiKeyService.mask_key(key, visible_chars=4)
    assert masked.endswith("f456")
    assert masked.startswith("*")
    assert len(masked) == len(key)


def test_validate_openai_key():
    """Тест валидации OpenAI ключа."""
    # Корректный ключ
    valid, error = ApiKeyService.validate_key_format('sk-proj-abc123def456ghi789', 'openai')
    assert valid is True
    assert error is None
    
    # Некорректный префикс
    valid, error = ApiKeyService.validate_key_format('invalid-key', 'openai')
    assert valid is False
    assert 'sk-' in error.lower()


def test_create_and_get_key(test_db_session, api_key_service):
    """Тест создания и получения ключа из БД."""
    # Создаём тестового пользователя
    from webapp.db.models import User, UserRole
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Создаём репозиторий
    repo = ApiKeyRepository(test_db_session)
    
    # Шифруем ключ
    plain_key = 'sk-proj-test123'
    encrypted_key = api_key_service.encrypt_key(plain_key)
    
    # Сохраняем в БД
    api_key = repo.create_key(
        user_id=user.id,
        provider='openai',
        key_ciphertext=encrypted_key
    )
    
    assert api_key.id is not None
    assert api_key.user_id == user.id
    assert api_key.provider == 'openai'
    assert api_key.key_ciphertext == encrypted_key
    
    # Получаем из БД
    retrieved = repo.get_by_provider(user.id, 'openai')
    assert retrieved is not None
    assert retrieved.id == api_key.id
    
    # Расшифровываем
    decrypted = api_key_service.decrypt_key(retrieved.key_ciphertext)
    assert decrypted == plain_key


def test_get_all_keys(test_db_session, api_key_service):
    """Тест получения всех ключей пользователя."""
    # Создаём тестового пользователя
    from webapp.db.models import User, UserRole
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    repo = ApiKeyRepository(test_db_session)
    
    # Создаём несколько ключей
    providers = ['openai', 'anthropic', 'deepseek']
    for provider in providers:
        encrypted = api_key_service.encrypt_key(f'key-{provider}')
        repo.create_key(user.id, provider, encrypted)
    
    # Получаем все ключи
    all_keys = repo.get_all_keys(user.id, include_shared=False)
    assert len(all_keys) == 3
    
    # Проверяем провайдеров
    retrieved_providers = [k.provider for k in all_keys]
    assert set(retrieved_providers) == set(providers)
