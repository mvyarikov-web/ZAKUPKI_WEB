"""
Репозиторий для работы с сессиями пользователей.

Управляет JWT-сессиями: создание, валидация, инвалидация, очистка истёкших.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from webapp.db.models import Session as SessionModel
from .base_repository import BaseRepository


class SessionRepository(BaseRepository[SessionModel]):
    """Репозиторий для управления пользовательскими сессиями."""
    
    def __init__(self, session: Session):
        """
        Инициализация репозитория сессий.
        
        Args:
            session: SQLAlchemy сессия
        """
        super().__init__(SessionModel, session)
    
    def create_session(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> SessionModel:
        """
        Создаёт новую сессию для пользователя.
        
        Args:
            user_id: ID пользователя
            token_hash: SHA-256 хеш JWT токена
            expires_at: Дата истечения токена
            ip_address: IP адрес клиента (опционально)
            user_agent: User-Agent браузера (опционально)
            
        Returns:
            Созданная сессия
            
        Example:
            >>> from datetime import datetime, timedelta
            >>> expires = datetime.utcnow() + timedelta(hours=24)
            >>> session = repo.create_session(
            ...     user_id=1,
            ...     token_hash='abc123...',
            ...     expires_at=expires,
            ...     ip_address='192.168.1.1'
            ... )
        """
        session_obj = SessionModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )
        
        self.session.add(session_obj)
        self.session.commit()
        self.session.refresh(session_obj)
        
        return session_obj
    
    def get_by_token_hash(self, token_hash: str) -> Optional[SessionModel]:
        """
        Получает сессию по хешу токена.
        
        Args:
            token_hash: SHA-256 хеш JWT токена
            
        Returns:
            Сессия или None, если не найдена
            
        Example:
            >>> session = repo.get_by_token_hash('abc123...')
            >>> if session and session.is_active:
            ...     print(f"Valid session for user {session.user_id}")
        """
        stmt = select(SessionModel).where(SessionModel.token_hash == token_hash)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_active_by_token_hash(self, token_hash: str) -> Optional[SessionModel]:
        """
        Получает активную сессию по хешу токена.
        
        Args:
            token_hash: SHA-256 хеш JWT токена
            
        Returns:
            Активная сессия или None
        """
        stmt = select(SessionModel).where(
            SessionModel.token_hash == token_hash,
            SessionModel.is_active == True,
            SessionModel.expires_at > datetime.utcnow()
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def invalidate_session(self, token_hash: str) -> bool:
        """
        Деактивирует сессию (logout).
        
        Args:
            token_hash: SHA-256 хеш JWT токена
            
        Returns:
            True если сессия найдена и деактивирована, False иначе
            
        Example:
            >>> success = repo.invalidate_session('abc123...')
            >>> if success:
            ...     print("Session logged out")
        """
        stmt = select(SessionModel).where(SessionModel.token_hash == token_hash)
        result = self.session.execute(stmt)
        session_obj = result.scalar_one_or_none()
        
        if session_obj:
            session_obj.is_active = False
            self.session.commit()
            return True
        
        return False
    
    def invalidate_all_user_sessions(self, user_id: int) -> int:
        """
        Деактивирует все сессии пользователя (logout everywhere).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество деактивированных сессий
        """
        stmt = select(SessionModel).where(
            SessionModel.user_id == user_id,
            SessionModel.is_active == True
        )
        result = self.session.execute(stmt)
        sessions = result.scalars().all()
        
        count = 0
        for session_obj in sessions:
            session_obj.is_active = False
            count += 1
        
        self.session.commit()
        return count
    
    def cleanup_expired(self) -> int:
        """
        Удаляет истёкшие сессии из БД (housekeeping).
        
        Returns:
            Количество удалённых сессий
            
        Note:
            Рекомендуется запускать периодически (например, через cron или job_queue)
            
        Example:
            >>> deleted_count = repo.cleanup_expired()
            >>> print(f"Cleaned up {deleted_count} expired sessions")
        """
        stmt = delete(SessionModel).where(
            SessionModel.expires_at < datetime.utcnow()
        )
        result = self.session.execute(stmt)
        self.session.commit()
        
        return result.rowcount
    
    def get_user_sessions(self, user_id: int, active_only: bool = False) -> list[SessionModel]:
        """
        Получает все сессии пользователя.
        
        Args:
            user_id: ID пользователя
            active_only: Только активные сессии (по умолчанию False)
            
        Returns:
            Список сессий пользователя
        """
        stmt = select(SessionModel).where(SessionModel.user_id == user_id)
        
        if active_only:
            stmt = stmt.where(
                SessionModel.is_active == True,
                SessionModel.expires_at > datetime.utcnow()
            )
        
        stmt = stmt.order_by(SessionModel.created_at.desc())
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def count_active_sessions(self, user_id: int) -> int:
        """
        Подсчитывает количество активных сессий пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество активных сессий
        """
        return self.count(
            SessionModel.user_id == user_id,
            SessionModel.is_active == True,
            SessionModel.expires_at > datetime.utcnow()
        )
