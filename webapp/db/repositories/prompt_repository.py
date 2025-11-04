"""
Репозиторий для работы с промптами.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from webapp.db.models import Prompt


class PromptRepository:
    """Репозиторий для работы с промптами."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_id(self, prompt_id: int) -> Optional[Prompt]:
        """Получить промпт по ID."""
        return self.db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    def get_by_user_id(self, user_id: int, include_shared: bool = True) -> List[Prompt]:
        """Получить все промпты пользователя (опционально + общие).
        
        Args:
            user_id: ID пользователя
            include_shared: включать ли общие (is_shared=True) промпты
        
        Returns:
            Список промптов
        """
        query = self.db.query(Prompt)
        
        if include_shared:
            # Промпты пользователя + общие промпты
            query = query.filter(
                or_(
                    Prompt.user_id == user_id,
                    Prompt.is_shared == True
                )
            )
        else:
            # Только промпты пользователя
            query = query.filter(Prompt.user_id == user_id)
        
        return query.order_by(Prompt.name).all()
    
    def get_by_name(self, user_id: int, name: str) -> Optional[Prompt]:
        """Получить промпт по имени пользователя."""
        return self.db.query(Prompt).filter(
            Prompt.user_id == user_id,
            Prompt.name == name
        ).first()
    
    def create(self, user_id: int, name: str, content: str, is_shared: bool = False) -> Prompt:
        """Создать новый промпт.
        
        Args:
            user_id: ID пользователя
            name: Название промпта
            content: Текст промпта
            is_shared: Доступен ли всем пользователям
        
        Returns:
            Созданный промпт
        """
        prompt = Prompt(
            user_id=user_id,
            name=name,
            content=content,
            is_shared=is_shared
        )
        self.db.add(prompt)
        self.db.commit()
        self.db.refresh(prompt)
        return prompt
    
    def update(self, prompt_id: int, **kwargs) -> Optional[Prompt]:
        """Обновить промпт.
        
        Args:
            prompt_id: ID промпта
            **kwargs: Поля для обновления (name, content, is_shared)
        
        Returns:
            Обновленный промпт или None
        """
        prompt = self.get_by_id(prompt_id)
        if not prompt:
            return None
        
        for key, value in kwargs.items():
            if hasattr(prompt, key):
                setattr(prompt, key, value)
        
        self.db.commit()
        self.db.refresh(prompt)
        return prompt
    
    def delete(self, prompt_id: int) -> bool:
        """Удалить промпт.
        
        Args:
            prompt_id: ID промпта
        
        Returns:
            True если удалено, False если не найдено
        """
        prompt = self.get_by_id(prompt_id)
        if not prompt:
            return False
        
        self.db.delete(prompt)
        self.db.commit()
        return True
    
    def get_shared(self) -> List[Prompt]:
        """Получить все общие (is_shared=True) промпты."""
        return self.db.query(Prompt).filter(Prompt.is_shared == True).order_by(Prompt.name).all()
