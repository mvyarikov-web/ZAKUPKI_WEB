"""
Repository для работы с API ключами провайдеров.

Управляет CRUD операциями над зашифрованными API ключами в БД.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from webapp.db.repositories.base_repository import BaseRepository
from webapp.db.models import APIKey


class ApiKeyRepository(BaseRepository[APIKey]):
    """Репозиторий для работы с API ключами."""
    
    def __init__(self, session: Session):
        """
        Инициализация репозитория.
        
        Args:
            session: SQLAlchemy сессия
        """
        super().__init__(APIKey, session)
    
    def create_key(
        self,
        user_id: int,
        provider: str,
        key_ciphertext: str,
        is_shared: bool = False
    ) -> APIKey:
        """
        Создать новый API ключ.
        
        Args:
            user_id: ID пользователя-владельца
            provider: Название провайдера (openai, anthropic, deepseek, etc.)
            key_ciphertext: Зашифрованный ключ (Fernet)
            is_shared: Доступен ли ключ всем пользователям (админский)
            
        Returns:
            Созданный APIKey
            
        Example:
            >>> repo = ApiKeyRepository(db_session)
            >>> key = repo.create_key(
            ...     user_id=1,
            ...     provider='openai',
            ...     key_ciphertext='gAAAA...'
            ... )
        """
        return self.create(
            user_id=user_id,
            provider=provider,
            key_ciphertext=key_ciphertext,
            is_shared=is_shared
        )
    
    def get_by_provider(self, user_id: int, provider: str) -> Optional[APIKey]:
        """
        Получить ключ пользователя для конкретного провайдера.
        
        Args:
            user_id: ID пользователя
            provider: Название провайдера
            
        Returns:
            APIKey или None если не найден
            
        Example:
            >>> key = repo.get_by_provider(user_id=1, provider='openai')
            >>> if key:
            ...     print(f"Found key for {key.provider}")
        """
        stmt = self.session.query(APIKey).filter(
            and_(
                APIKey.user_id == user_id,
                APIKey.provider == provider
            )
        )
        return stmt.first()
    
    def get_all_keys(self, user_id: int, include_shared: bool = True) -> List[APIKey]:
        """
        Получить все ключи пользователя.
        
        Args:
            user_id: ID пользователя
            include_shared: Включить ли общие (is_shared=True) ключи
            
        Returns:
            Список APIKey
            
        Example:
            >>> keys = repo.get_all_keys(user_id=1)
            >>> for key in keys:
            ...     print(f"{key.provider}: {key.is_shared}")
        """
        if include_shared:
            # Свои ключи + общие ключи (is_shared=True)
            stmt = self.session.query(APIKey).filter(
                (APIKey.user_id == user_id) | (APIKey.is_shared == True)
            )
        else:
            # Только свои ключи
            stmt = self.session.query(APIKey).filter(
                APIKey.user_id == user_id
            )
        
        return stmt.order_by(APIKey.provider, APIKey.created_at.desc()).all()
    
    def get_shared_keys(self) -> List[APIKey]:
        """
        Получить все общие ключи (is_shared=True).
        
        Returns:
            Список общих APIKey
            
        Example:
            >>> shared = repo.get_shared_keys()
            >>> print(f"Found {len(shared)} shared keys")
        """
        return self.find_all(is_shared=True)
    
    def update_key(self, key_id: int, new_ciphertext: str) -> Optional[APIKey]:
        """
        Обновить зашифрованный ключ.
        
        Args:
            key_id: ID ключа
            new_ciphertext: Новый зашифрованный ключ
            
        Returns:
            Обновлённый APIKey или None
            
        Example:
            >>> updated = repo.update_key(key_id=5, new_ciphertext='gAAAA...')
        """
        return self.update(key_id, key_ciphertext=new_ciphertext)
    
    def delete_key(self, key_id: int) -> bool:
        """
        Удалить API ключ.
        
        Args:
            key_id: ID ключа
            
        Returns:
            True если удалён, False если не найден
            
        Example:
            >>> success = repo.delete_key(key_id=5)
        """
        return self.delete(key_id)
    
    def get_by_provider_with_fallback(
        self,
        user_id: int,
        provider: str
    ) -> Optional[APIKey]:
        """
        Получить ключ пользователя для провайдера с fallback на общий.
        
        Сначала ищет личный ключ пользователя, если не найден — берёт общий (is_shared=True).
        
        Args:
            user_id: ID пользователя
            provider: Название провайдера
            
        Returns:
            APIKey (личный или общий) или None
            
        Example:
            >>> key = repo.get_by_provider_with_fallback(user_id=1, provider='openai')
            >>> if key:
            ...     if key.is_shared:
            ...         print("Using shared admin key")
            ...     else:
            ...         print("Using personal key")
        """
        # Сначала ищем личный ключ
        personal_key = self.get_by_provider(user_id, provider)
        if personal_key:
            return personal_key
        
        # Fallback на общий ключ
        stmt = self.session.query(APIKey).filter(
            and_(
                APIKey.provider == provider,
                APIKey.is_shared == True
            )
        ).order_by(APIKey.created_at.desc())
        
        return stmt.first()
