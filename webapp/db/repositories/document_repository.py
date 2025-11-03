"""
Репозиторий для работы с документами.
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from webapp.db.models import Document
from webapp.db.repositories.base_repository import BaseRepository


# Импортируем Enum для type hints
try:
    from webapp.db.models import DocumentStatus
except ImportError:
    # Fallback для старых версий models.py
    class DocumentStatus:  # type: ignore
        PENDING = 'new'
        PROCESSING = 'parsed'
        INDEXED = 'indexed'
        FAILED = 'error'


class DocumentRepository(BaseRepository[Document]):
    """
    Репозиторий для работы с документами.
    """
    
    def __init__(self, session: Session):
        super().__init__(Document, session)
    
    def create_document(
        self,
        owner_id: int,
        original_filename: str,
        size_bytes: int,
        sha256: str,
        content_type: Optional[str] = None,
        blob: Optional[bytes] = None,
        storage_url: Optional[str] = None
    ) -> Document:
        """
        Создать новый документ.
        
        Args:
            owner_id: ID владельца документа
            original_filename: Имя файла
            size_bytes: Размер в байтах
            sha256: SHA256 хэш
            content_type: MIME тип (опционально)
            blob: Содержимое файла < 10MB (опционально)
            storage_url: URL хранилища для > 50MB (опционально)
            
        Returns:
            Созданный Document
        """
        return self.create(
            owner_id=owner_id,
            original_filename=original_filename,
            size_bytes=size_bytes,
            sha256=sha256,
            content_type=content_type,
            blob=blob,
            storage_url=storage_url,
            status=DocumentStatus.PENDING.value
        )
    
    def get_by_owner(
        self,
        owner_id: int,
        status: Optional[DocumentStatus] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Document]:
        """
        Получить документы владельца.
        
        Args:
            owner_id: ID владельца
            status: Фильтр по статусу (опционально)
            limit: Макс. кол-во записей
            offset: Смещение
            
        Returns:
            Список Document
        """
        if status:
            status_val = status.value if isinstance(status, DocumentStatus) else status
            return self.find_all(limit=limit, offset=offset, owner_id=owner_id, status=status_val)
        return self.find_all(limit=limit, offset=offset, owner_id=owner_id)
    
    def get_by_hash(self, sha256: str, owner_id: Optional[int] = None) -> Optional[Document]:
        """
        Найти документ по хэшу (опционально в пределах владельца).
        
        Args:
            sha256: SHA256 хэш
            owner_id: ID владельца (опционально)
            
        Returns:
            Document или None
        """
        if owner_id:
            return self.find_one(sha256=sha256, owner_id=owner_id)
        return self.find_one(sha256=sha256)
    
    def update_status(
        self,
        document_id: int,
        status: DocumentStatus
    ) -> Optional[Document]:
        """
        Обновить статус документа.
        
        Args:
            document_id: ID документа
            status: Новый статус
            
        Returns:
            Обновлённый Document или None
        """
        updates = {"status": status.value if isinstance(status, DocumentStatus) else status}
        if status == DocumentStatus.INDEXED or (isinstance(status, str) and status == DocumentStatus.INDEXED.value):
            updates["indexed_at"] = datetime.utcnow()
        return self.update(document_id, **updates)
    
    def mark_indexed(self, document_id: int, chunk_count: int = 0) -> Optional[Document]:
        """
        Пометить документ как проиндексированный.
        
        Args:
            document_id: ID документа
            chunk_count: Количество чанков
            
        Returns:
            Обновлённый Document или None
        """
        return self.update(
            document_id,
            status=DocumentStatus.INDEXED.value,
            indexed_at=datetime.utcnow()
        )
    
    def mark_failed(self, document_id: int) -> Optional[Document]:
        """
        Пометить документ как неудачно обработанный.
        
        Args:
            document_id: ID документа
            
        Returns:
            Обновлённый Document или None
        """
        return self.update(
            document_id,
            status=DocumentStatus.FAILED.value
        )
    
    def get_pending_documents(self, limit: Optional[int] = None) -> List[Document]:
        """
        Получить документы в статусе PENDING для обработки.
        
        Args:
            limit: Макс. кол-во
            
        Returns:
            Список Document
        """
        return self.find_all(limit=limit, status=DocumentStatus.PENDING.value)
    
    def count_by_owner(self, owner_id: int, status: Optional[DocumentStatus] = None) -> int:
        """
        Подсчитать документы владельца.
        
        Args:
            owner_id: ID владельца
            status: Фильтр по статусу (опционально)
            
        Returns:
            Количество документов
        """
        if status:
            status_val = status.value if isinstance(status, DocumentStatus) else status
            return self.count(owner_id=owner_id, status=status_val)
        return self.count(owner_id=owner_id)
