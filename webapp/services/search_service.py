"""
Сервис поиска с поддержкой keyword, semantic и hybrid режимов.
"""
from typing import List, Tuple, Optional, Dict
import openai
from sqlalchemy import or_

from webapp.db.repositories import ChunkRepository, SearchHistoryRepository
from webapp.db.models import Chunk


class SearchResult:
    """Результат поиска с метаданными."""
    
    def __init__(
        self,
        chunk: Chunk,
        score: float,
        snippet: str,
        document_id: int,
        document_name: str
    ):
        self.chunk = chunk
        self.score = score
        self.snippet = snippet
        self.document_id = document_id
        self.document_name = document_name
    
    def to_dict(self) -> dict:
        """Преобразовать в словарь для JSON."""
        return {
            'chunk_id': self.chunk.id,
            'document_id': self.document_id,
            'document_name': self.document_name,
            'text': self.chunk.text,
            'snippet': self.snippet,
            'score': self.score,
            'chunk_idx': self.chunk.chunk_idx
        }


class SearchService:
    """
    Сервис поиска по документам:
    - keyword_search: полнотекстовый поиск по chunks.text
    - semantic_search: векторный поиск через pgvector
    - hybrid_search: комбинация keyword + semantic с весами
    - save_to_history: запись в search_history
    """
    
    # Параметры по умолчанию
    DEFAULT_LIMIT = 10
    DEFAULT_KEYWORD_WEIGHT = 0.3
    DEFAULT_SEMANTIC_WEIGHT = 0.7
    SNIPPET_LENGTH = 200
    
    # OpenAI
    EMBEDDING_MODEL = "text-embedding-3-small"
    
    def __init__(
        self,
        chunk_repo: ChunkRepository,
        history_repo: SearchHistoryRepository,
        openai_api_key: Optional[str] = None
    ):
        """
        Args:
            chunk_repo: ChunkRepository
            history_repo: SearchHistoryRepository
            openai_api_key: OpenAI API ключ (опционально)
        """
        self.chunk_repo = chunk_repo
        self.history_repo = history_repo
        
        if openai_api_key:
            openai.api_key = openai_api_key
    
    @staticmethod
    def make_snippet(text: str, query: str, length: int = SNIPPET_LENGTH) -> str:
        """
        Создать сниппет текста с подсветкой запроса.
        
        Args:
            text: Полный текст
            query: Поисковый запрос
            length: Длина сниппета
            
        Returns:
            Сниппет с контекстом вокруг первого вхождения запроса
        """
        if not query or not text:
            return text[:length] + ('...' if len(text) > length else '')
        
        # Ищем первое вхождение (регистронезависимо)
        query_lower = query.lower()
        text_lower = text.lower()
        pos = text_lower.find(query_lower)
        
        if pos == -1:
            # Запрос не найден - возвращаем начало
            return text[:length] + ('...' if len(text) > length else '')
        
        # Вычисляем границы сниппета
        start = max(0, pos - length // 2)
        end = min(len(text), start + length)
        
        snippet = text[start:end]
        if start > 0:
            snippet = '...' + snippet
        if end < len(text):
            snippet = snippet + '...'
        
        return snippet
    
    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Сгенерировать embedding для поискового запроса.
        
        Args:
            query: Текст запроса
            
        Returns:
            Вектор embedding (1536 dimensions)
        """
        try:
            response = openai.embeddings.create(
                input=[query],
                model=self.EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Ошибка генерации embedding: {e}")
            return [0.0] * 1536  # Fallback
    
    def keyword_search(
        self,
        query: str,
        user_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        limit: int = DEFAULT_LIMIT
    ) -> List[SearchResult]:
        """
        Полнотекстовый поиск по chunks.text.
        
        Args:
            query: Поисковый запрос
            user_id: Фильтр по владельцу (опционально)
            document_ids: Фильтр по документам (опционально)
            limit: Макс. кол-во результатов
            
        Returns:
            Список SearchResult
        """
        # Простой SQL LIKE поиск (для production лучше использовать FTS)
        from sqlalchemy import select
        
        stmt = select(Chunk).where(Chunk.text.ilike(f'%{query}%'))
        
        if user_id is not None:
            stmt = stmt.where(Chunk.owner_id == user_id)
        
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        
        stmt = stmt.limit(limit)
        
        chunks = list(self.chunk_repo.session.execute(stmt).scalars().all())
        
        results = []
        for chunk in chunks:
            # Простая оценка - количество вхождений запроса
            score = chunk.text.lower().count(query.lower()) / max(len(chunk.text.split()), 1)
            
            snippet = self.make_snippet(chunk.text, query)
            
            # Получаем имя документа
            doc_name = chunk.document.original_filename if chunk.document else "Unknown"
            
            results.append(SearchResult(
                chunk=chunk,
                score=score,
                snippet=snippet,
                document_id=chunk.document_id,
                document_name=doc_name
            ))
        
        # Сортируем по score
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results
    
    def semantic_search(
        self,
        query: str,
        user_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        limit: int = DEFAULT_LIMIT,
        min_similarity: float = 0.5
    ) -> List[SearchResult]:
        """
        Векторный поиск через pgvector.
        
        Args:
            query: Поисковый запрос
            user_id: Фильтр по владельцу (опционально)
            document_ids: Фильтр по документам (опционально)
            limit: Макс. кол-во результатов
            min_similarity: Минимальная cosine similarity (0.0-1.0)
            
        Returns:
            Список SearchResult
        """
        # Генерируем embedding для запроса
        query_embedding = self.generate_query_embedding(query)
        
        # Векторный поиск
        vector_results = self.chunk_repo.vector_search(
            query_embedding=query_embedding,
            user_id=user_id,
            document_ids=document_ids,
            limit=limit,
            min_similarity=min_similarity
        )
        
        results = []
        for chunk, similarity in vector_results:
            snippet = self.make_snippet(chunk.text, query)
            doc_name = chunk.document.original_filename if chunk.document else "Unknown"
            
            results.append(SearchResult(
                chunk=chunk,
                score=similarity,
                snippet=snippet,
                document_id=chunk.document_id,
                document_name=doc_name
            ))
        
        return results
    
    def hybrid_search(
        self,
        query: str,
        user_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        limit: int = DEFAULT_LIMIT,
        keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
        semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT
    ) -> List[SearchResult]:
        """
        Гибридный поиск: комбинация keyword + semantic.
        
        Args:
            query: Поисковый запрос
            user_id: Фильтр по владельцу
            document_ids: Фильтр по документам
            limit: Макс. кол-во результатов
            keyword_weight: Вес полнотекстового поиска (0.0-1.0)
            semantic_weight: Вес векторного поиска (0.0-1.0)
            
        Returns:
            Список SearchResult с комбинированным score
        """
        # Получаем результаты обоих методов
        keyword_results = self.keyword_search(query, user_id, document_ids, limit * 2)
        semantic_results = self.semantic_search(query, user_id, document_ids, limit * 2)
        
        # Объединяем результаты по chunk_id
        combined: Dict[int, SearchResult] = {}
        
        # Добавляем keyword результаты
        for result in keyword_results:
            chunk_id = result.chunk.id
            result.score = result.score * keyword_weight
            combined[chunk_id] = result
        
        # Добавляем semantic результаты
        for result in semantic_results:
            chunk_id = result.chunk.id
            if chunk_id in combined:
                # Комбинируем scores
                combined[chunk_id].score += result.score * semantic_weight
            else:
                result.score = result.score * semantic_weight
                combined[chunk_id] = result
        
        # Сортируем по комбинированному score
        results = sorted(combined.values(), key=lambda x: x.score, reverse=True)
        
        return results[:limit]
    
    def save_to_history(
        self,
        user_id: int,
        query: str,
        results_count: int,
        filters: Optional[dict] = None
    ) -> None:
        """
        Сохранить запрос в историю поиска.
        
        Args:
            user_id: ID пользователя
            query: Текст запроса
            results_count: Количество результатов
            filters: Дополнительные фильтры (опционально)
        """
        self.history_repo.create_search_record(
            user_id=user_id,
            query_text=query,
            results_count=results_count,
            filters=filters
        )
