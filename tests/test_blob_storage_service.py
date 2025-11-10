"""
Тесты для blob_storage_service (инкремент 020).
Проверка загрузки файлов в documents.blob и дедупликации.
"""

import io
import pytest
from werkzeug.datastructures import FileStorage

from webapp.services.blob_storage_service import BlobStorageService
from webapp.db.models import Document, UserDocument
from webapp.config.config_service import ConfigService


@pytest.fixture
def blob_service():
    """Создать экземпляр BlobStorageService."""
    config = ConfigService()
    return BlobStorageService(config)


def test_calculate_sha256(blob_service):
    """Тест расчёта SHA256 и чтения байтов."""
    content = b"Hello, World!"
    stream = io.BytesIO(content)
    
    sha256, file_bytes = blob_service.calculate_sha256(stream)
    
    assert sha256 == "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
    assert file_bytes == content


def test_save_file_to_db_new_file(db, test_user, blob_service):
    """Тест сохранения нового файла в БД."""
    import uuid
    
    # Подготовить тестовый файл с уникальным контентом
    content = f"Test file content for blob storage {uuid.uuid4()}".encode()
    file_storage = FileStorage(
        stream=io.BytesIO(content),
        filename="test_document.txt",
        content_type="text/plain"
    )
    
    # Сохранить файл
    doc, is_new = blob_service.save_file_to_db(
        db=db,
        file=file_storage,
        user_id=test_user.id,
        user_path="/uploads/test_document.txt",
        mime_type="text/plain"
    )
    
    assert is_new is True
    assert doc.id is not None
    assert doc.blob == content
    assert doc.size_bytes == len(content)
    assert doc.mime == "text/plain"
    
    # Проверить связь user_documents
    link = db.query(UserDocument).filter(
        UserDocument.user_id == test_user.id,
        UserDocument.document_id == doc.id
    ).first()
    
    assert link is not None
    assert link.original_filename == "test_document.txt"
    assert link.user_path == "/uploads/test_document.txt"
    assert link.is_soft_deleted is False


def test_save_file_to_db_duplicate(db, test_user, blob_service):
    """Тест дедупликации: повторная загрузка того же файла возвращает тот же документ."""
    import uuid
    
    # Уникальный контент для этого теста
    content = f"Duplicate test content {uuid.uuid4()}".encode()
    
    # Первая загрузка
    file1 = FileStorage(
        stream=io.BytesIO(content),
        filename="file1.txt",
        content_type="text/plain"
    )
    doc1, is_new1 = blob_service.save_file_to_db(
        db=db,
        file=file1,
        user_id=test_user.id,
        user_path="/uploads/file1.txt"
    )
    
    assert is_new1 is True
    initial_doc_id = doc1.id
    
    # Вторая загрузка (тот же контент, тот же путь)
    file2 = FileStorage(
        stream=io.BytesIO(content),
        filename="file1_copy.txt",  # Другое имя
        content_type="text/plain"
    )
    doc2, is_new2 = blob_service.save_file_to_db(
        db=db,
        file=file2,
        user_id=test_user.id,
        user_path="/uploads/file1.txt"  # Тот же путь
    )
    
    assert is_new2 is False  # Не новый документ
    assert doc1.id == doc2.id  # Тот же документ
    
    # Проверить что существует только одна связь (uq_user_document constraint)
    links = db.query(UserDocument).filter(
        UserDocument.user_id == test_user.id,
        UserDocument.document_id == initial_doc_id
    ).all()
    
    assert len(links) == 1
    assert links[0].user_path == "/uploads/file1.txt"


def test_get_file_bytes(db, test_user, blob_service):
    """Тест получения байтов файла из БД."""
    content = b"Content to retrieve"
    file_storage = FileStorage(
        stream=io.BytesIO(content),
        filename="retrieve_test.txt"
    )
    
    doc, _ = blob_service.save_file_to_db(
        db=db,
        file=file_storage,
        user_id=test_user.id,
        user_path="/uploads/retrieve_test.txt"
    )
    
    # Получить байты
    retrieved_bytes = blob_service.get_file_bytes(db, doc.id)
    
    assert retrieved_bytes == content


def test_get_file_stream(db, test_user, blob_service):
    """Тест получения потока для чтения файла."""
    content = b"Stream test content"
    file_storage = FileStorage(
        stream=io.BytesIO(content),
        filename="stream_test.txt"
    )
    
    doc, _ = blob_service.save_file_to_db(
        db=db,
        file=file_storage,
        user_id=test_user.id,
        user_path="/uploads/stream_test.txt"
    )
    
    # Получить поток
    stream = blob_service.get_file_stream(db, doc.id)
    
    assert stream is not None
    assert stream.read() == content


def test_get_file_nonexistent(db, blob_service):
    """Тест получения несуществующего файла."""
    result = blob_service.get_file_bytes(db, 99999)
    assert result is None
    
    stream = blob_service.get_file_stream(db, 99999)
    assert stream is None


@pytest.mark.skip(reason="Требует настроенной БД с данными для prune")
def test_check_size_limit_and_prune(db, test_user, blob_service):
    """Тест автоматического удаления 30% при превышении лимита."""
    # TODO: Реализовать после настройки тестовой БД
    pass
