"""
Тесты для DocumentUploadService.

Проверяет валидацию, SHA256, дедупликацию и сохранение в БД.
"""

import pytest
from io import BytesIO
from werkzeug.datastructures import FileStorage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from webapp.db.base import Base
from webapp.db.repositories import DocumentRepository
from webapp.services.document_upload_service import DocumentUploadService


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
def upload_service(test_db_session):
    """Создаёт DocumentUploadService."""
    repo = DocumentRepository(test_db_session)
    return DocumentUploadService(repo)


def test_calculate_sha256():
    """Тест расчёта SHA256."""
    data = b"Hello, world!"
    sha256 = DocumentUploadService.calculate_sha256(data)
    
    assert len(sha256) == 64
    assert sha256 == "315f5bdb76d078c43b8ac0064e4a0164612b1fce77c869345bfc94c75894edd3"


def test_validate_file_success():
    """Тест успешной валидации файла."""
    valid, error = DocumentUploadService.validate_file(
        "test.pdf",
        1024,
        "application/pdf"
    )
    
    assert valid is True
    assert error is None


def test_validate_file_no_extension():
    """Тест файла без расширения."""
    valid, error = DocumentUploadService.validate_file(
        "testfile",
        1024
    )
    
    assert valid is False
    assert "без расширения" in error


def test_validate_file_unsupported_extension():
    """Тест неподдерживаемого расширения."""
    valid, error = DocumentUploadService.validate_file(
        "test.exe",
        1024
    )
    
    assert valid is False
    assert "Неподдерживаемое расширение" in error


def test_validate_file_too_large():
    """Тест слишком большого файла."""
    valid, error = DocumentUploadService.validate_file(
        "test.pdf",
        200 * 1024 * 1024  # 200 МБ
    )
    
    assert valid is False
    assert "превышает лимит" in error


def test_save_document_success(upload_service, test_db_session):
    """Тест успешного сохранения документа."""
    # Создаём тестового пользователя
    from webapp.db.models import User, UserRole
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Сохраняем документ
    file_data = b"Test document content"
    document, error = upload_service.save_document(
        owner_id=user.id,
        filename="test.txt",
        file_data=file_data,
        content_type="text/plain"
    )
    
    assert document is not None
    assert error is None
    assert document.original_filename == "test.txt"
    assert document.size_bytes == len(file_data)
    assert document.blob == file_data
    assert document.sha256 is not None


def test_save_document_duplicate(upload_service, test_db_session):
    """Тест дедупликации при повторной загрузке."""
    # Создаём тестового пользователя
    from webapp.db.models import User, UserRole
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    file_data = b"Unique content"
    
    # Первая загрузка
    doc1, error1 = upload_service.save_document(
        owner_id=user.id,
        filename="test.txt",
        file_data=file_data
    )
    assert doc1 is not None
    assert error1 is None
    
    # Вторая загрузка того же файла
    doc2, error2 = upload_service.save_document(
        owner_id=user.id,
        filename="test_copy.txt",  # другое имя, но тот же контент
        file_data=file_data
    )
    
    assert doc2 is None
    assert error2 is not None
    assert "уже существует" in error2


def test_save_from_werkzeug(upload_service, test_db_session):
    """Тест сохранения из Werkzeug FileStorage."""
    # Создаём пользователя
    from webapp.db.models import User, UserRole
    user = User(
        email='test@example.com',
        password_hash='hash123',
        role=UserRole.USER
    )
    test_db_session.add(user)
    test_db_session.commit()
    
    # Создаём FileStorage
    file_data = b"Test file content"
    file_storage = FileStorage(
        stream=BytesIO(file_data),
        filename="test.pdf",
        content_type="application/pdf"
    )
    
    # Сохраняем
    document, error = upload_service.save_from_werkzeug(
        owner_id=user.id,
        file=file_storage
    )
    
    assert document is not None
    assert error is None
    assert document.original_filename == "test.pdf"
    assert document.content_type == "application/pdf"
