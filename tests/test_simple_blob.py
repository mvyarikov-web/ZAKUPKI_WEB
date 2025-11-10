"""Простой тест для отладки индексации."""
import uuid
from io import BytesIO
from werkzeug.datastructures import FileStorage

def test_simple_blob_indexing(db, test_user, app):
    """Минимальный тест: сохранение blob → проверка что blob сохранён."""
    from webapp.services.blob_storage_service import BlobStorageService
    from webapp.config.config_service import ConfigService
    
    config = ConfigService()
    blob_service = BlobStorageService(config)
    
    unique_id = str(uuid.uuid4())[:8]
    content = f"Test content {unique_id}"
    file_bytes = content.encode('utf-8')
    
    fake_file = FileStorage(
        stream=BytesIO(file_bytes),
        filename=f"simple_test_{unique_id}.txt",
        content_type="text/plain"
    )
    
    document, is_new = blob_service.save_file_to_db(
        db=db,
        file=fake_file,
        user_id=test_user.id,
        user_path=f"simple/{unique_id}.txt"
    )
    
    print(f"\nDocument created:")
    print(f"  ID: {document.id}")
    print(f"  SHA256: {document.sha256[:16]}...")
    print(f"  Blob size: {len(document.blob) if document.blob else 0} bytes")
    print(f"  Size bytes: {document.size_bytes}")
    print(f"  Is new: {is_new}")
    
    assert is_new is True
    assert document.blob is not None
    assert len(document.blob) == len(file_bytes)
    
    # Проверяем что blob действительно содержит наш контент
    retrieved = document.blob.tobytes() if hasattr(document.blob, 'tobytes') else bytes(document.blob)
    assert retrieved == file_bytes
    print(f"  ✓ Blob content matches")
