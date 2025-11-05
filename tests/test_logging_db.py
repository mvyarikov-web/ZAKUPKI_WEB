"""
Тесты для DatabaseLogHandler и AppLogRepository.

Проверяет запись логов в БД, маскирование секретов, фильтрацию.
"""

import pytest
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from webapp.db.base import Base
from webapp.db.repositories import AppLogRepository
from webapp.logging import DatabaseLogHandler


@pytest.fixture(scope='function')
def test_db_session():
    """Создаёт изолированную тестовую БД в памяти."""
    test_engine = create_engine(
        'sqlite:///:memory:',
        echo=False,
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def log_repository(test_db_session):
    """Создаёт AppLogRepository."""
    return AppLogRepository(test_db_session)


def test_create_log(log_repository):
    """Тест создания лога."""
    log = log_repository.create_log(
        level='INFO',
        message='Test message',
        component='test_component'
    )
    
    assert log.id is not None
    assert log.level == 'INFO'
    assert log.message == 'Test message'
    assert log.component == 'test_component'


def test_get_logs_by_level(log_repository):
    """Тест фильтрации по уровню."""
    # Создаём логи разных уровней
    log_repository.create_log(level='INFO', message='Info message')
    log_repository.create_log(level='ERROR', message='Error message')
    log_repository.create_log(level='WARNING', message='Warning message')
    
    # Получаем только ERROR
    error_logs = log_repository.get_logs(level='ERROR')
    
    assert len(error_logs) == 1
    assert error_logs[0].level == 'ERROR'


def test_get_errors(log_repository):
    """Тест получения ошибок."""
    # Создаём разные логи
    log_repository.create_log(level='INFO', message='Info')
    log_repository.create_log(level='ERROR', message='Error 1')
    log_repository.create_log(level='CRITICAL', message='Critical')
    log_repository.create_log(level='ERROR', message='Error 2')
    
    # Получаем только ERROR и CRITICAL
    errors = log_repository.get_errors()
    
    assert len(errors) == 3
    assert all(log.level in ['ERROR', 'CRITICAL'] for log in errors)


def test_delete_old_logs(log_repository, test_db_session):
    """Тест удаления старых логов."""
    
    # Создаём старый лог (вручную ставим дату)
    old_log = log_repository.create_log(level='INFO', message='Old message')
    old_log.created_at = datetime.utcnow() - timedelta(days=40)
    test_db_session.commit()
    
    # Создаём новый лог
    log_repository.create_log(level='INFO', message='New message')
    
    # Удаляем записи старше 30 дней
    deleted = log_repository.delete_old(days=30)
    
    assert deleted == 1
    
    # Проверяем, что осталась только новая запись
    remaining = log_repository.get_logs()
    assert len(remaining) == 1
    assert remaining[0].message == 'New message'


def test_mask_secrets():
    """Тест маскирования секретов."""
    # API ключи
    message1 = "Using key: sk-proj-abc123def456ghi789"
    masked1 = DatabaseLogHandler.mask_secrets(message1)
    assert "sk-proj-****" in masked1
    assert "abc123def456ghi789" not in masked1
    
    # Пароли
    message2 = '{"password": "secretpass123"}'
    masked2 = DatabaseLogHandler.mask_secrets(message2)
    assert "secretpass123" not in masked2
    assert "****" in masked2
    
    # Токены
    message3 = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    masked3 = DatabaseLogHandler.mask_secrets(message3)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in masked3
    assert "Bearer ****" in masked3


def test_database_log_handler_emit(test_db_session):
    """Тест записи через DatabaseLogHandler."""
    # Создаём фабрику сессий
    def session_factory():
        return test_db_session
    
    # Создаём handler
    handler = DatabaseLogHandler(
        session_factory=session_factory,
        component='test_app'
    )
    
    # Создаём logger
    logger = logging.getLogger('test_logger')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    # Логируем сообщение
    logger.info("Test log message")
    
    # Проверяем, что запись создана
    repo = AppLogRepository(test_db_session)
    logs = repo.get_logs()
    
    assert len(logs) >= 1
    assert any("Test log message" in log.message for log in logs)


def test_database_log_handler_with_secrets(test_db_session):
    """Тест маскирования секретов через handler."""
    def session_factory():
        return test_db_session
    
    handler = DatabaseLogHandler(
        session_factory=session_factory,
        component='test_app'
    )
    
    logger = logging.getLogger('test_secrets')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    # Логируем сообщение с API ключом
    logger.info("API Key: sk-proj-verysecretkey123456")
    
    # Проверяем маскирование
    repo = AppLogRepository(test_db_session)
    logs = repo.get_logs()
    
    assert len(logs) >= 1
    log_with_key = [log for log in logs if "API Key" in log.message][0]
    assert "verysecretkey123456" not in log_with_key.message
    assert "sk-proj-****" in log_with_key.message


def test_get_logs_with_date_range(log_repository, test_db_session):
    """Тест фильтрации по диапазону дат."""
    
    # Создаём логи с разными датами
    log1 = log_repository.create_log(level='INFO', message='Log 1')
    log1.created_at = datetime.utcnow() - timedelta(days=10)
    
    log2 = log_repository.create_log(level='INFO', message='Log 2')
    log2.created_at = datetime.utcnow() - timedelta(days=5)
    
    log_repository.create_log(level='INFO', message='Log 3')
    # log3 имеет текущую дату
    
    test_db_session.commit()
    
    # Получаем логи за последние 7 дней
    start_date = datetime.utcnow() - timedelta(days=7)
    recent_logs = log_repository.get_logs(start_date=start_date)
    
    assert len(recent_logs) == 2
    assert all(log.created_at >= start_date for log in recent_logs)


def test_count_by_level(log_repository):
    """Тест подсчёта логов по уровню."""
    # Создаём несколько логов одного уровня
    for i in range(3):
        log_repository.create_log(level='ERROR', message=f'Error {i}')
    
    for i in range(2):
        log_repository.create_log(level='INFO', message=f'Info {i}')
    
    # Подсчитываем
    error_count = log_repository.count_by_level('ERROR')
    info_count = log_repository.count_by_level('INFO')
    
    assert error_count == 3
    assert info_count == 2
