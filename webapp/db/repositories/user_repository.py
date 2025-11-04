"""
Репозиторий для работы с пользователями.
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from webapp.db.models import User
from webapp.db.repositories.base_repository import BaseRepository


# Импортируем Enum для type hints
try:
    from webapp.db.models import UserRole
except ImportError:
    # Fallback для старых версий models.py
    class UserRole:  # type: ignore
        USER = 'user'
        ADMIN = 'admin'


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями.
    """
    
    def __init__(self, session: Session):
        super().__init__(User, session)
    
    def get_by_email(self, email: str) -> Optional[User]:
        """
        Получить пользователя по email.
        
        Args:
            email: Email пользователя
            
        Returns:
            Объект User или None
        """
        return self.find_one(email=email)
    
    def create_user(
        self,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER
    ) -> User:
        """
        Создать нового пользователя.
        
        Args:
            email: Email пользователя
            password_hash: Хэш пароля (bcrypt)
            role: Роль пользователя (по умолчанию USER)
            
        Returns:
            Созданный User
        """
        return self.create(
            email=email,
            password_hash=password_hash,
            role=role.value
        )
    
    def update_password(self, user_id: int, new_password_hash: str) -> Optional[User]:
        """
        Обновить пароль пользователя.
        
        Args:
            user_id: ID пользователя
            new_password_hash: Новый хэш пароля
            
        Returns:
            Обновлённый User или None
        """
        return self.update(user_id, password_hash=new_password_hash)
    
    def get_all_users(self, limit: Optional[int] = None, offset: int = 0):
        """
        Получить список всех пользователей.
        
        Args:
            limit: Макс. кол-во записей
            offset: Смещение
            
        Returns:
            Список User
        """
        return self.find_all(limit=limit, offset=offset)
    
    def update_user_name(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> bool:
        """
        Обновить имя и фамилию пользователя.
        
        Args:
            user_id: ID пользователя
            first_name: Имя (необязательно)
            last_name: Фамилия (необязательно)
            
        Returns:
            True если успешно, False иначе
        """
        update_data = {}
        if first_name is not None:
            update_data['first_name'] = first_name
        if last_name is not None:
            update_data['last_name'] = last_name
        
        if not update_data:
            return True  # Нечего обновлять
        
        result = self.update(user_id, **update_data)
        return result is not None
    
    def update_user_email(self, user_id: int, new_email: str) -> bool:
        """
        Обновить email пользователя.
        
        Args:
            user_id: ID пользователя
            new_email: Новый email
            
        Returns:
            True если успешно, False иначе
        """
        result = self.update(user_id, email=new_email)
        return result is not None
