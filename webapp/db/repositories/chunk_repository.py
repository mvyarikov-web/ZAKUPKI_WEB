"""
Репозиторий для работы с чанками документов и векторным поиском.
"""
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from webapp.db.models import Chunk
from webapp.db.repositories.base_repository import BaseRepository


class ChunkRepository(BaseRepository[Chunk]):
    """
    Репозиторий для работы с чанками и векторным поиском.
    """
    
    def __init__(self, session: Session):
        super().__init__(Chunk, session)
    
    def create_chunk(
        self,
        document_id: int,
        owner_id: int,
        text: str,
        chunk_idx: int,
        embedding: Optional[List[float]] = None,
        text_sha256: Optional[str] = None,
        tokens: Optional[int] = None
    ) -> Chunk:
        """
        Создать новый чанк.
        
        Args:
            document_id: ID документа
            owner_id: ID владельца
            text: Текстовое содержимое
            chunk_idx: Порядковый номер чанка в документе
            embedding: Вектор эмбеддинга (1536 измерений)
            text_sha256: SHA256 хэш текста (опционально)
            tokens: Количество токенов (опционально)
            
        Returns:
            Созданный Chunk
        """
        return self.create(
            document_id=document_id,
            owner_id=owner_id,
            text=text,
            chunk_idx=chunk_idx,
            embedding=embedding,
            text_sha256=text_sha256,
            tokens=tokens
        )
    
    def create_many(self, chunks_data: List[dict]) -> List[Chunk]:
        """
        Создать несколько чанков за один раз (bulk insert).
        
        Args:
            chunks_data: Список словарей с данными чанков
            
        Returns:
            Список созданных Chunk
        """
        chunks = [Chunk(**data) for data in chunks_data]
        self.session.add_all(chunks)
        self.session.commit()
        for chunk in chunks:
            self.session.refresh(chunk)
        return chunks
    
    def get_by_document(
        self,
        document_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Chunk]:
        """
        Получить чанки документа.
        
        Args:
            document_id: ID документа
            limit: Макс. кол-во
            offset: Смещение
            
        Returns:
            Список Chunk отсортированный по chunk_idx
        """
        stmt = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_idx)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())
    
    def update_embedding(self, chunk_id: int, embedding: List[float]) -> Optional[Chunk]:
        """
        Обновить эмбеддинг чанка.
        
        Args:
            chunk_id: ID чанка
            embedding: Новый вектор эмбеддинга
            
        Returns:
            Обновлённый Chunk или None
        """
        return self.update(chunk_id, embedding=embedding)
    
    def vector_search(
        self,
        query_embedding: List[float],
        user_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        limit: int = 5,
        min_similarity: float = 0.0
    ) -> List[Tuple[Chunk, float]]:
        """
        Векторный поиск по эмбеддингам (cosine similarity).
        
        Args:
            query_embedding: Вектор запроса (1536 измерений)
            user_id: Фильтр по владельцу документов (опционально)
            document_ids: Фильтр по ID документов (опционально)
            limit: Макс. кол-во результатов
            min_similarity: Минимальная схожесть (0.0 - 1.0)
            
        Returns:
            Список кортежей (Chunk, similarity_score)
        """
        # Базовый запрос с cosine similarity через pgvector
        # 1 - (embedding <=> query) даёт cosine similarity от 0 до 1
        stmt = select(
            Chunk,
            (1 - Chunk.embedding.cosine_distance(query_embedding)).label("similarity")
        ).where(Chunk.embedding.isnot(None))
        
        # Фильтр по owner_id
        if user_id is not None:
            stmt = stmt.where(Chunk.owner_id == user_id)
        
        # Фильтр по document_ids
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        
        # Фильтр по минимальной схожести
        if min_similarity > 0:
            stmt = stmt.where(
                (1 - Chunk.embedding.cosine_distance(query_embedding)) >= min_similarity
            )
        
        # Сортировка по убыванию similarity
        stmt = stmt.order_by(text("similarity DESC")).limit(limit)
        
        results = self.session.execute(stmt).all()
        return [(row[0], row[1]) for row in results]
    
    def delete_by_document(self, document_id: int) -> int:
        """
        Удалить все чанки документа.
        
        Args:
            document_id: ID документа
            
        Returns:
            Количество удалённых записей
        """
        chunks = self.get_by_document(document_id)
        count = len(chunks)
        for chunk in chunks:
            self.session.delete(chunk)
        self.session.commit()
        return count
    
    def count_by_document(self, document_id: int) -> int:
        """
        Подсчитать чанки документа.
        
        Args:
            document_id: ID документа
            
        Returns:
            Количество чанков
        """
        return self.count(document_id=document_id)
    
    def get_chunks_without_embeddings(self, limit: Optional[int] = None) -> List[Chunk]:
        """
        Получить чанки без эмбеддингов для обработки.
        
        Args:
            limit: Макс. кол-во
            
        Returns:
            Список Chunk
        """
        stmt = select(Chunk).where(Chunk.embedding.is_(None))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())
