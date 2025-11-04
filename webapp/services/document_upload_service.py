"""
Сервис загрузки документов с валидацией и дедупликацией.
"""
import hashlib
import mimetypes
from typing import Optional, Tuple
from werkzeug.datastructures import FileStorage

from webapp.db.repositories import DocumentRepository
from webapp.db.models import Document


class DocumentUploadService:
    """
    Сервис для загрузки документов в БД.
    
    Выполняет:
    - Валидацию размера, MIME-типа, расширения
    - Расчёт SHA256 для дедупликации
    - Сохранение в БД (bytea для <10MB, URL для >50MB)
    """
    
    # Поддерживаемые расширения
    ALLOWED_EXTENSIONS = {
        'txt', 'pdf', 'docx', 'doc', 'xlsx', 'xls',
        'zip', 'rar', 'png', 'jpg', 'jpeg'
    }
    
    # Лимиты размера
    MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 МБ
    BLOB_THRESHOLD = 10 * 1024 * 1024   # 10 МБ - порог для blob
    EXTERNAL_THRESHOLD = 50 * 1024 * 1024  # 50 МБ - порог для S3/MinIO
    
    def __init__(self, repository: DocumentRepository):
        """
        Args:
            repository: DocumentRepository для работы с БД
        """
        self.repository = repository
    
    @staticmethod
    def calculate_sha256(file_data: bytes) -> str:
        """
        Рассчитать SHA256 хэш файла.
        
        Args:
            file_data: Данные файла
            
        Returns:
            SHA256 хэш в hex формате
        """
        return hashlib.sha256(file_data).hexdigest()
    
    @staticmethod
    def validate_file(
        filename: str,
        size_bytes: int,
        content_type: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить файл на соответствие требованиям.
        
        Args:
            filename: Имя файла
            size_bytes: Размер в байтах
            content_type: MIME-тип (опционально)
            
        Returns:
            (success, error_message)
        """
        # Проверка расширения
        if '.' not in filename:
            return False, "Файл без расширения"
        
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in DocumentUploadService.ALLOWED_EXTENSIONS:
            return False, f"Неподдерживаемое расширение: .{ext}"
        
        # Проверка размера
        if size_bytes <= 0:
            return False, "Пустой файл"
        
        if size_bytes > DocumentUploadService.MAX_SIZE_BYTES:
            max_mb = DocumentUploadService.MAX_SIZE_BYTES // (1024 * 1024)
            return False, f"Файл превышает лимит {max_mb} МБ"
        
        # MIME валидация (опционально)
        if content_type:
            # Разрешаем только безопасные MIME
            safe_types = [
                'text/', 'application/pdf', 'application/vnd.',
                'application/zip', 'application/x-rar', 'image/'
            ]
            if not any(content_type.startswith(t) for t in safe_types):
                return False, f"Недопустимый MIME-тип: {content_type}"
        
        return True, None
    
    def check_duplicate(self, sha256: str, owner_id: int) -> Optional[Document]:
        """
        Проверить, существует ли документ с таким хэшем у владельца.
        
        Args:
            sha256: SHA256 хэш
            owner_id: ID владельца
            
        Returns:
            Существующий Document или None
        """
        return self.repository.get_by_sha256_and_owner(sha256, owner_id)
    
    def save_document(
        self,
        owner_id: int,
        filename: str,
        file_data: bytes,
        content_type: Optional[str] = None
    ) -> Tuple[Optional[Document], Optional[str]]:
        """
        Сохранить документ в БД.
        
        Args:
            owner_id: ID владельца
            filename: Имя файла
            file_data: Данные файла
            content_type: MIME-тип
            
        Returns:
            (document, error_message)
        """
        size_bytes = len(file_data)
        
        # Валидация
        valid, error = self.validate_file(filename, size_bytes, content_type)
        if not valid:
            return None, error
        
        # Расчёт SHA256
        sha256 = self.calculate_sha256(file_data)
        
        # Проверка дубликата
        existing = self.check_duplicate(sha256, owner_id)
        if existing:
            return None, f"Файл уже существует (ID: {existing.id})"
        
        # Определяем способ хранения
        blob = None
        storage_url = None
        
        if size_bytes < self.BLOB_THRESHOLD:
            # < 10 МБ - в blob
            blob = file_data
        elif size_bytes < self.EXTERNAL_THRESHOLD:
            # 10-50 МБ - в blob (для упрощения)
            blob = file_data
        else:
            # > 50 МБ - требуется внешнее хранилище
            # TODO: интеграция с S3/MinIO
            return None, "Файлы >50 МБ требуют внешнего хранилища (не реализовано)"
        
        # Сохраняем в БД
        try:
            document = self.repository.create_document(
                owner_id=owner_id,
                original_filename=filename,
                size_bytes=size_bytes,
                sha256=sha256,
                content_type=content_type,
                blob=blob,
                storage_url=storage_url
            )
            return document, None
        except Exception as e:
            return None, f"Ошибка сохранения в БД: {str(e)}"
    
    def save_from_werkzeug(
        self,
        owner_id: int,
        file: FileStorage
    ) -> Tuple[Optional[Document], Optional[str]]:
        """
        Сохранить файл из Flask/Werkzeug FileStorage.
        
        Args:
            owner_id: ID владельца
            file: FileStorage объект
            
        Returns:
            (document, error_message)
        """
        if not file or not file.filename:
            return None, "Файл не выбран"
        
        # Читаем данные
        try:
            file_data = file.read()
        except Exception as e:
            return None, f"Ошибка чтения файла: {str(e)}"
        
        # Определяем MIME
        content_type = file.content_type
        if not content_type:
            content_type, _ = mimetypes.guess_type(file.filename)
        
        return self.save_document(
            owner_id=owner_id,
            filename=file.filename,
            file_data=file_data,
            content_type=content_type
        )
