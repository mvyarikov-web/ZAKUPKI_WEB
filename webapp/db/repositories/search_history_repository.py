"""
Репозиторий для работы с историей поиска.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from webapp.db.models import SearchHistory
from webapp.db.repositories.base_repository import BaseRepository


class SearchHistoryRepository(BaseRepository[SearchHistory]):
    """
    Репозиторий для работы с историей поисковых запросов.
    """
    
    def __init__(self, session: Session):
        super().__init__(SearchHistory, session)
    
    def create_search_record(
        self,
        user_id: int,
        query_text: str,
        results_count: int,
        filters: Optional[dict] = None
    ) -> SearchHistory:
        """
        Создать запись о поисковом запросе.
        
        Args:
            user_id: ID пользователя
            query_text: Текст запроса
            results_count: Количество результатов
            filters: Дополнительные фильтры (опционально)
            
        Returns:
            Созданный SearchHistory
        """
        return self.create(
            user_id=user_id,
            query_text=query_text,
            results_count=results_count,
            filters=filters
        )
    
    def get_by_user(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[SearchHistory]:
        """
        Получить историю поиска пользователя.
        
        Args:
            user_id: ID пользователя
            limit: Макс. кол-во
            offset: Смещение
            
        Returns:
            Список SearchHistory, отсортированный по дате (новые первые)
        """
        stmt = (
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.created_at))
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())
    
    def get_recent(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[SearchHistory]:
        """
        Получить последние N запросов пользователя.
        
        Args:
            user_id: ID пользователя
            limit: Количество запросов
            
        Returns:
            Список последних SearchHistory
        """
        return self.get_by_user(user_id, limit=limit)
    
    def delete_old(
        self,
        days: int = 30,
        user_id: Optional[int] = None
    ) -> int:
        """
        Удалить старые записи истории.
        
        Args:
            days: Удалить записи старше N дней
            user_id: Фильтр по пользователю (опционально)
            
        Returns:
            Количество удалённых записей
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(SearchHistory).where(SearchHistory.created_at < cutoff_date)
        if user_id is not None:
            stmt = stmt.where(SearchHistory.user_id == user_id)
        
        records = list(self.session.execute(stmt).scalars().all())
        count = len(records)
        
        for record in records:
            self.session.delete(record)
        self.session.commit()
        
        return count
    
    def count_by_user(self, user_id: int) -> int:
        """
        Подсчитать количество запросов пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество записей
        """
        return self.count(user_id=user_id)
