"""
Адаптер для совместимости legacy кода с новым БД-сервисом API ключей.
Предоставляет совместимый интерфейс для получения ключей из БД.
"""
import logging
from typing import Optional
from flask import g

from webapp.services.api_keys_service import APIKeysService
from webapp.db.base import SessionLocal

logger = logging.getLogger(__name__)


class APIKeysManagerAdapter:
    """
    Адаптер для совместимости с legacy кодом.
    Предоставляет методы get_key() для получения ключей из БД.
    """
    
    def __init__(self):
        """Инициализация адаптера"""
        self.db_session = None
        self.service = None
        self._init_service()
    
    def _init_service(self):
        """Инициализирует сервис для работы с БД"""
        try:
            self.db_session = SessionLocal()
            self.service = APIKeysService(self.db_session)
        except Exception as e:
            logger.error(f"Ошибка инициализации сервиса API ключей: {e}")
            self.service = None
    
    def _get_user_id(self) -> Optional[int]:
        """Получает ID текущего пользователя"""
        try:
            # Пробуем получить из g.current_user (если авторизован)
            if hasattr(g, 'current_user') and g.current_user:
                return g.current_user.id
            
            # Если не авторизован, используем первого пользователя (fallback для обратной совместимости)
            # Это временное решение, в идеале все запросы должны быть авторизованы
            from webapp.db.models import User
            first_user = self.db_session.query(User).first()
            if first_user:
                logger.warning(f"Используется fallback на первого пользователя ID={first_user.id}")
                return first_user.id
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения user_id: {e}")
            return None
    
    def get_key(self, provider: str) -> Optional[str]:
        """
        Получает API ключ для провайдера (совместимый метод).
        
        Args:
            provider: Провайдер ('openai', 'deepseek', 'perplexity')
        
        Returns:
            str или None: Расшифрованный API ключ или None если не найден
        """
        if not self.service:
            logger.error("Сервис API ключей не инициализирован")
            return None
        
        user_id = self._get_user_id()
        if not user_id:
            logger.error("Не удалось определить user_id для получения ключа")
            return None
        
        try:
            return self.service.get_key(user_id, provider)
        except Exception as e:
            logger.error(f"Ошибка получения ключа {provider} для user_id={user_id}: {e}")
            return None
    
    def get_all_keys(self) -> dict:
        """
        Получает все ключи пользователя (совместимый метод).
        
        Returns:
            dict: Словарь {provider: api_key}
        """
        if not self.service:
            return {}
        
        user_id = self._get_user_id()
        if not user_id:
            return {}
        
        try:
            return self.service.get_all_keys(user_id)
        except Exception as e:
            logger.error(f"Ошибка получения всех ключей для user_id={user_id}: {e}")
            return {}


def get_api_keys_manager():
    """
    Фабричная функция для получения менеджера API ключей.
    Заменяет get_api_keys_manager_multiple() из legacy кода.
    
    Returns:
        APIKeysManagerAdapter: Адаптер для работы с ключами
    """
    return APIKeysManagerAdapter()
