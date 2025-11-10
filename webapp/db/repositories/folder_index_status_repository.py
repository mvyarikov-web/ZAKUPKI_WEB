"""Репозиторий для работы с folder_index_status."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from webapp.db.models import FolderIndexStatus
from webapp.db.repositories.base_repository import BaseRepository


class FolderIndexStatusRepository(BaseRepository[FolderIndexStatus]):
    """Репозиторий для статусов индексации папок."""
    
    def __init__(self, db: Session):
        super().__init__(db, FolderIndexStatus)
    
    def get_status(self, owner_id: int, folder_path: str) -> Optional[FolderIndexStatus]:
        """
        Получить статус индексации папки.
        
        Args:
            owner_id: ID владельца
            folder_path: Путь к папке
            
        Returns:
            Статус индексации или None
        """
        return self.db.query(FolderIndexStatus).filter(
            FolderIndexStatus.owner_id == owner_id,
            FolderIndexStatus.folder_path == folder_path
        ).first()
    
    def upsert_status(
        self,
        owner_id: int,
        folder_path: str,
        root_hash: Optional[str] = None,
        last_indexed_at: Optional[datetime] = None
    ) -> FolderIndexStatus:
        """
        Создать или обновить статус индексации папки.
        
        Args:
            owner_id: ID владельца
            folder_path: Путь к папке
            root_hash: Хэш содержимого папки
            last_indexed_at: Время последней индексации
            
        Returns:
            Статус индексации
        """
        status = self.get_status(owner_id, folder_path)
        
        if status:
            # Обновляем существующий
            if root_hash is not None:
                status.root_hash = root_hash
            if last_indexed_at is not None:
                status.last_indexed_at = last_indexed_at
        else:
            # Создаём новый
            status = FolderIndexStatus(
                owner_id=owner_id,
                folder_path=folder_path,
                root_hash=root_hash,
                last_indexed_at=last_indexed_at or datetime.utcnow()
            )
            self.db.add(status)
        
        self.db.flush()
        return status
    
    def delete_status(self, owner_id: int, folder_path: str) -> bool:
        """
        Удалить статус индексации папки.
        
        Args:
            owner_id: ID владельца
            folder_path: Путь к папке
            
        Returns:
            True если удалено, False если не найдено
        """
        status = self.get_status(owner_id, folder_path)
        if status:
            self.db.delete(status)
            return True
        return False
