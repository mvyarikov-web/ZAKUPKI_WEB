"""
Репозиторий для работы с системными логами.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, or_
from webapp.db.models import AppLog
from webapp.db.repositories.base_repository import BaseRepository


class AppLogRepository(BaseRepository[AppLog]):
    """
    Репозиторий для работы с системными логами.
    """
    
    def __init__(self, session: Session):
        super().__init__(AppLog, session)
    
    def create_log(
        self,
        level: str,
        message: str,
        component: Optional[str] = None,
        user_id: Optional[int] = None,
        context_json: Optional[dict] = None
    ) -> AppLog:
        """
        Создать запись лога.
        
        Args:
            level: Уровень лога (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Сообщение
            component: Имя компонента/модуля
            user_id: ID пользователя (опционально)
            context_json: Дополнительный контекст (опционально)
            
        Returns:
            Созданный AppLog
        """
        return self.create(
            level=level,
            message=message,
            component=component,
            user_id=user_id,
            context_json=context_json
        )
    
    def get_logs(
        self,
        level: Optional[str] = None,
        user_id: Optional[int] = None,
        component: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[AppLog]:
        """
        Получить логи с фильтрами.
        
        Args:
            level: Фильтр по уровню
            user_id: Фильтр по пользователю
            component: Фильтр по компоненту
            start_date: Начало периода
            end_date: Конец периода
            limit: Макс. кол-во
            offset: Смещение
            
        Returns:
            Список AppLog, отсортированный по дате (новые первые)
        """
        stmt = select(AppLog)
        
        # Фильтры
        if level is not None:
            stmt = stmt.where(AppLog.level == level)
        
        if user_id is not None:
            stmt = stmt.where(AppLog.user_id == user_id)
        
        if component is not None:
            stmt = stmt.where(AppLog.component == component)
        
        if start_date is not None:
            stmt = stmt.where(AppLog.created_at >= start_date)
        
        if end_date is not None:
            stmt = stmt.where(AppLog.created_at <= end_date)
        
        # Сортировка и пагинация
        stmt = stmt.order_by(desc(AppLog.created_at)).offset(offset)
        
        if limit is not None:
            stmt = stmt.limit(limit)
        
        return list(self.session.execute(stmt).scalars().all())
    
    def get_errors(
        self,
        limit: int = 100,
        user_id: Optional[int] = None
    ) -> List[AppLog]:
        """
        Получить последние ошибки (ERROR и CRITICAL).
        
        Args:
            limit: Макс. кол-во
            user_id: Фильтр по пользователю (опционально)
            
        Returns:
            Список AppLog
        """
        stmt = (
            select(AppLog)
            .where(or_(AppLog.level == 'ERROR', AppLog.level == 'CRITICAL'))
            .order_by(desc(AppLog.created_at))
            .limit(limit)
        )
        
        if user_id is not None:
            stmt = stmt.where(AppLog.user_id == user_id)
        
        return list(self.session.execute(stmt).scalars().all())
    
    def delete_old(
        self,
        days: int = 30,
        level: Optional[str] = None
    ) -> int:
        """
        Удалить старые логи.
        
        Args:
            days: Удалить записи старше N дней
            level: Фильтр по уровню (опционально)
            
        Returns:
            Количество удалённых записей
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(AppLog).where(AppLog.created_at < cutoff_date)
        
        if level is not None:
            stmt = stmt.where(AppLog.level == level)
        
        records = list(self.session.execute(stmt).scalars().all())
        count = len(records)
        
        for record in records:
            self.session.delete(record)
        self.session.commit()
        
        return count
    
    def count_by_level(self, level: str) -> int:
        """
        Подсчитать количество логов по уровню.
        
        Args:
            level: Уровень лога
            
        Returns:
            Количество записей
        """
        return self.count(level=level)
