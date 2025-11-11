"""
Сервис для работы с хранением файлов в documents.blob (DB MODE).
Инкремент 020: полный отказ от файловой системы.
"""

import hashlib
import io
from typing import BinaryIO, Optional, Tuple
from datetime import datetime

from werkzeug.datastructures import FileStorage
from sqlalchemy.orm import Session

from webapp.db.models import Document, UserDocument
from webapp.config.config_service import ConfigService


class BlobStorageService:
    """Сервис для загрузки и хранения файлов в БД."""
    
    def __init__(self, config: ConfigService):
        self.config = config
    
    def calculate_sha256(self, file_stream: BinaryIO) -> Tuple[str, bytes]:
        """
        Вычислить SHA256 и прочитать содержимое файла.
        
        Args:
            file_stream: Поток для чтения файла
            
        Returns:
            Tuple[sha256_hash, file_bytes]
        """
        hasher = hashlib.sha256()
        chunks = []
        
        # Читаем файл чанками для экономии памяти
        while True:
            chunk = file_stream.read(8192)  # 8KB chunks
            if not chunk:
                break
            hasher.update(chunk)
            chunks.append(chunk)
        
        file_bytes = b''.join(chunks)
        return hasher.hexdigest(), file_bytes
    
    def save_file_to_db(
        self,
        db: Session,
        file: FileStorage,
        user_id: int,
        user_path: str,
        mime_type: Optional[str] = None
    ) -> Tuple[Document, bool]:
        """
        Сохранить файл в documents.blob (DB MODE).
        
        Args:
            db: Сессия БД
            file: Загружаемый файл (Werkzeug FileStorage)
            user_id: ID пользователя
            user_path: Путь файла у пользователя
            mime_type: MIME-тип файла (опционально)
            
        Returns:
            Tuple[Document, is_new]: документ и флаг новизны
        """
        # 1. Считать SHA256 и байты файла
        sha256_hash, file_bytes = self.calculate_sha256(file.stream)
        size_bytes = len(file_bytes)
        
        # 2. Проверить дедупликацию
        existing_doc = db.query(Document).filter(
            Document.sha256 == sha256_hash
        ).first()
        
        if existing_doc:
            # Документ уже существует, проверяем существующую связь
            existing_link = db.query(UserDocument).filter(
                UserDocument.user_id == user_id,
                UserDocument.document_id == existing_doc.id,
                UserDocument.user_path == user_path  # Учитываем путь
            ).first()
            
            if not existing_link:
                # Создать новую связь пользователь-документ
                new_link = UserDocument(
                    user_id=user_id,
                    document_id=existing_doc.id,
                    original_filename=file.filename,
                    user_path=user_path,
                    is_soft_deleted=False
                )
                db.add(new_link)
                db.commit()
            elif existing_link.is_soft_deleted:
                # Восстановить мягко удалённый документ
                existing_link.is_soft_deleted = False
                existing_link.original_filename = file.filename  # Обновить имя
                existing_link.updated_at = datetime.utcnow()
                db.commit()
            
            return existing_doc, False  # Не новый
        
        # 2.5. Проверяем лимит ДО добавления нового документа и при необходимости выполняем prune
        ok = self.check_size_limit_and_prune(db, size_bytes)
        if not ok:
            raise RuntimeError('Недостаточно места в БД после prune')
        
        # 3. Создать новый документ с blob
        new_doc = Document(
            sha256=sha256_hash,
            size_bytes=size_bytes,
            mime=mime_type or file.content_type or 'application/octet-stream',
            blob=file_bytes,  # Сохранить байты в БД
            parse_status='pending',
            created_at=datetime.utcnow()
        )
        db.add(new_doc)
        db.flush()  # Получить ID документа
        
        # 4. Создать связь пользователь-документ
        new_link = UserDocument(
            user_id=user_id,
            document_id=new_doc.id,
            original_filename=file.filename,
            user_path=user_path,
            is_soft_deleted=False
        )
        db.add(new_link)
        db.commit()
        
        return new_doc, True  # Новый документ
    
    def get_file_bytes(self, db: Session, document_id: int) -> Optional[bytes]:
        """
        Получить байты файла из БД.
        
        Args:
            db: Сессия БД
            document_id: ID документа
            
        Returns:
            Байты файла или None если не найдено
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        return doc.blob if doc else None
    
    def get_file_stream(self, db: Session, document_id: int) -> Optional[io.BytesIO]:
        """
        Получить поток для чтения файла из БД.
        
        Args:
            db: Сессия БД
            document_id: ID документа
            
        Returns:
            BytesIO поток или None
        """
        file_bytes = self.get_file_bytes(db, document_id)
        return io.BytesIO(file_bytes) if file_bytes else None
    
    def check_size_limit_and_prune(self, db: Session, new_file_size: int) -> bool:
        """
        Проверить лимит БД и при необходимости удалить 30% файлов с минимальным retention score.
        
        Args:
            db: Сессия БД
            new_file_size: Размер нового файла в байтах
            
        Returns:
            True если места достаточно (возможно после prune), False если не удалось освободить
        """
        from sqlalchemy import text
        
        # 0. Проверяем, включён ли автоматический prune через app_settings
        auto_prune_enabled_row = db.execute(
            text("SELECT value FROM app_settings WHERE key = 'AUTO_PRUNE_ENABLED'")
        ).fetchone()
        
        auto_prune_enabled = True  # По умолчанию включён
        if auto_prune_enabled_row:
            auto_prune_enabled = auto_prune_enabled_row[0].lower() == 'true'
        
        # 1. Получить текущий объём
        current_size = db.execute(
            text("SELECT COALESCE(SUM(size_bytes), 0) FROM documents WHERE blob IS NOT NULL")
        ).scalar()
        
        # 1.5. Читаем лимит из app_settings (если есть), иначе из конфига
        db_size_limit_row = db.execute(
            text("SELECT value FROM app_settings WHERE key = 'DB_SIZE_LIMIT_BYTES'")
        ).fetchone()
        
        if db_size_limit_row:
            limit = int(db_size_limit_row[0])
        else:
            limit = self.config.db_size_limit_bytes
        
        # 2. Проверить нужен ли prune
        if current_size + new_file_size <= limit:
            return True  # Места достаточно
        
        # 3. Если автоочистка отключена — сразу возвращаем False
        if not auto_prune_enabled:
            return False
        
        # 4. Выполнить prune 30%
        db.execute(text("""
            WITH ranked AS (
                SELECT d.id,
                    (
                        0.5 * LN(d.access_count + 1)
                        - 0.3 * EXTRACT(DAY FROM (NOW() - COALESCE(d.last_accessed_at, d.created_at)))
                        + 0.2 * (COALESCE(d.indexing_cost_seconds, 0) / 60.0)
                    ) AS score,
                    ROW_NUMBER() OVER (ORDER BY (
                        0.5 * LN(d.access_count + 1)
                        - 0.3 * EXTRACT(DAY FROM (NOW() - COALESCE(d.last_accessed_at, d.created_at)))
                        + 0.2 * (COALESCE(d.indexing_cost_seconds, 0) / 60.0)
                    ) ASC) AS rn,
                    COUNT(*) OVER () AS total
                FROM documents d
                WHERE d.blob IS NOT NULL
            )
            DELETE FROM documents d
            USING ranked r
            WHERE d.id = r.id
              AND r.rn <= FLOOR(0.3 * r.total)::BIGINT
        """))
        db.commit()
        
        # 5. Проверить снова после удаления
        new_current_size = db.execute(
            text("SELECT COALESCE(SUM(size_bytes), 0) FROM documents WHERE blob IS NOT NULL")
        ).scalar()
        
        return new_current_size + new_file_size <= limit
