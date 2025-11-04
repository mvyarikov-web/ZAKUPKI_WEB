"""
Сервис для работы с промптами.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from webapp.db.repositories.prompt_repository import PromptRepository
from webapp.db.models import Prompt


class PromptService:
    """Сервис для работы с промптами."""
    
    def __init__(self, db: Session):
        self.repo = PromptRepository(db)
    
    def get_user_prompts(self, user_id: int, include_shared: bool = True) -> List[Dict[str, Any]]:
        """Получить промпты пользователя в формате JSON.
        
        Args:
            user_id: ID пользователя
            include_shared: включать ли общие промпты
        
        Returns:
            Список промптов в формате словарей
        """
        prompts = self.repo.get_by_user_id(user_id, include_shared)
        return [self._prompt_to_dict(p) for p in prompts]
    
    def get_prompt_by_id(self, prompt_id: int) -> Optional[Dict[str, Any]]:
        """Получить промпт по ID."""
        prompt = self.repo.get_by_id(prompt_id)
        return self._prompt_to_dict(prompt) if prompt else None
    
    def get_prompt_by_name(self, user_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Получить промпт по имени."""
        prompt = self.repo.get_by_name(user_id, name)
        return self._prompt_to_dict(prompt) if prompt else None
    
    def create_prompt(self, user_id: int, name: str, content: str, is_shared: bool = False) -> Dict[str, Any]:
        """Создать новый промпт.
        
        Args:
            user_id: ID пользователя
            name: Название промпта
            content: Текст промпта
            is_shared: Доступен ли всем
        
        Returns:
            Созданный промпт в формате словаря
        
        Raises:
            ValueError: если промпт с таким именем уже существует
        """
        # Проверяем, нет ли уже промпта с таким именем у пользователя
        existing = self.repo.get_by_name(user_id, name)
        if existing:
            raise ValueError(f"Промпт с именем '{name}' уже существует")
        
        prompt = self.repo.create(user_id, name, content, is_shared)
        return self._prompt_to_dict(prompt)
    
    def update_prompt(self, prompt_id: int, user_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Обновить промпт.
        
        Args:
            prompt_id: ID промпта
            user_id: ID пользователя (для проверки прав)
            **kwargs: Поля для обновления
        
        Returns:
            Обновленный промпт или None если не найден/нет прав
        """
        # Проверяем права
        prompt = self.repo.get_by_id(prompt_id)
        if not prompt or prompt.user_id != user_id:
            return None
        
        # Если обновляется имя, проверяем уникальность
        if 'name' in kwargs:
            existing = self.repo.get_by_name(user_id, kwargs['name'])
            if existing and existing.id != prompt_id:
                raise ValueError(f"Промпт с именем '{kwargs['name']}' уже существует")
        
        updated = self.repo.update(prompt_id, **kwargs)
        return self._prompt_to_dict(updated) if updated else None
    
    def delete_prompt(self, prompt_id: int, user_id: int) -> bool:
        """Удалить промпт.
        
        Args:
            prompt_id: ID промпта
            user_id: ID пользователя (для проверки прав)
        
        Returns:
            True если удалено, False если не найдено/нет прав
        """
        # Проверяем права
        prompt = self.repo.get_by_id(prompt_id)
        if not prompt or prompt.user_id != user_id:
            return False
        
        return self.repo.delete(prompt_id)
    
    def get_shared_prompts(self) -> List[Dict[str, Any]]:
        """Получить все общие промпты."""
        prompts = self.repo.get_shared()
        return [self._prompt_to_dict(p) for p in prompts]
    
    @staticmethod
    def _prompt_to_dict(prompt: Prompt) -> Dict[str, Any]:
        """Конвертировать промпт в словарь."""
        return {
            'id': prompt.id,
            'user_id': prompt.user_id,
            'name': prompt.name,
            'content': prompt.content,
            'is_shared': prompt.is_shared,
            'created_at': prompt.created_at.isoformat() if prompt.created_at else None,
            'updated_at': prompt.updated_at.isoformat() if prompt.updated_at else None,
        }
