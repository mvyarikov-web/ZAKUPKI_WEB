"""
Сервис для управления API ключами через БД.
Заменяет legacy файловое хранилище.
"""
import logging
from typing import Optional, List, Dict, Any
from cryptography.fernet import Fernet
from flask import current_app

from webapp.db.models import APIKey
from webapp.db.base import SessionLocal

logger = logging.getLogger(__name__)


class APIKeysService:
    """Сервис для работы с API ключами в БД"""
    
    def __init__(self, db_session=None):
        """
        Инициализация сервиса.
        
        Args:
            db_session: SQLAlchemy сессия (если None, создаётся новая)
        """
        self.db_session = db_session or SessionLocal()
        
        # Получаем ключ шифрования из конфигурации
        fernet_key = current_app.config.get('FERNET_ENCRYPTION_KEY')
        if not fernet_key:
            raise ValueError("FERNET_ENCRYPTION_KEY не настроен в конфигурации")
        
        self.cipher = Fernet(fernet_key.encode())
    
    def _encrypt_key(self, api_key: str) -> str:
        """Шифрует API ключ"""
        return self.cipher.encrypt(api_key.encode()).decode('utf-8')
    
    def _decrypt_key(self, encrypted_key: str) -> str:
        """Расшифровывает API ключ"""
        return self.cipher.decrypt(encrypted_key.encode()).decode('utf-8')
    
    def add_key(self, user_id: int, provider: str, api_key: str, 
                is_shared: bool = False) -> APIKey:
        """
        Добавляет новый API ключ для пользователя.
        
        Args:
            user_id: ID пользователя
            provider: Провайдер (openai, deepseek, perplexity)
            api_key: API ключ в открытом виде
            is_shared: Доступен ли ключ другим пользователям
        
        Returns:
            APIKey: Созданный объект ключа
        """
        encrypted = self._encrypt_key(api_key)
        
        key = APIKey(
            user_id=user_id,
            provider=provider,
            key_ciphertext=encrypted,
            is_shared=is_shared
        )
        
        self.db_session.add(key)
        self.db_session.commit()
        
        logger.info(f"Добавлен API ключ для пользователя {user_id}, провайдер: {provider}")
        return key
    
    def get_key(self, user_id: int, provider: str) -> Optional[str]:
        """
        Получает расшифрованный API ключ для провайдера.
        Сначала ищет личный ключ пользователя, затем общие ключи.
        
        Args:
            user_id: ID пользователя
            provider: Провайдер
        
        Returns:
            str или None: Расшифрованный API ключ или None если не найден
        """
        # Сначала ищем личный ключ
        key = self.db_session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.provider == provider
        ).first()
        
        # Если личного нет, ищем общий
        if not key:
            key = self.db_session.query(APIKey).filter(
                APIKey.provider == provider,
                APIKey.is_shared
            ).first()
        
        if key:
            return self._decrypt_key(key.key_ciphertext)
        
        return None
    
    def get_all_keys(self, user_id: int) -> Dict[str, Optional[str]]:
        """
        Получает все ключи пользователя (личные + общие).
        
        Args:
            user_id: ID пользователя
        
        Returns:
            Dict: Словарь {provider: decrypted_key}
        """
        result = {}
        providers = ['openai', 'deepseek', 'perplexity']
        
        for provider in providers:
            key = self.get_key(user_id, provider)
            if key:
                result[provider] = key
        
        return result
    
    def list_keys_info(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получает информацию о всех ключах пользователя (без расшифровки).
        
        Args:
            user_id: ID пользователя
        
        Returns:
            List[Dict]: Список словарей с информацией о ключах
        """
        # Личные ключи
        personal_keys = self.db_session.query(APIKey).filter(
            APIKey.user_id == user_id
        ).all()
        
        # Общие ключи (если у пользователя нет личного для этого провайдера)
        personal_providers = {k.provider for k in personal_keys}
        shared_keys = self.db_session.query(APIKey).filter(
            APIKey.is_shared,
            ~APIKey.provider.in_(personal_providers)
        ).all()
        
        result = []
        
        for key in personal_keys:
            decrypted = self._decrypt_key(key.key_ciphertext)
            result.append({
                'id': key.id,
                'provider': key.provider,
                'key_preview': f"{decrypted[:15]}...{decrypted[-5:]}" if len(decrypted) > 20 else decrypted,
                'is_shared': key.is_shared,
                'is_personal': True,
                'created_at': key.created_at.isoformat()
            })
        
        for key in shared_keys:
            decrypted = self._decrypt_key(key.key_ciphertext)
            result.append({
                'id': key.id,
                'provider': key.provider,
                'key_preview': f"{decrypted[:15]}...{decrypted[-5:]}" if len(decrypted) > 20 else decrypted,
                'is_shared': True,
                'is_personal': False,
                'created_at': key.created_at.isoformat()
            })
        
        return result
    
    def update_key(self, user_id: int, provider: str, new_api_key: str) -> bool:
        """
        Обновляет существующий ключ пользователя.
        
        Args:
            user_id: ID пользователя
            provider: Провайдер
            new_api_key: Новый API ключ
        
        Returns:
            bool: True если обновление успешно
        """
        key = self.db_session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.provider == provider
        ).first()
        
        if not key:
            return False
        
        key.key_ciphertext = self._encrypt_key(new_api_key)
        self.db_session.commit()
        
        logger.info(f"Обновлён API ключ для пользователя {user_id}, провайдер: {provider}")
        return True
    
    def delete_key(self, user_id: int, provider: str) -> bool:
        """
        Удаляет ключ пользователя.
        
        Args:
            user_id: ID пользователя
            provider: Провайдер
        
        Returns:
            bool: True если удаление успешно
        """
        key = self.db_session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.provider == provider
        ).first()
        
        if not key:
            return False
        
        self.db_session.delete(key)
        self.db_session.commit()
        
        logger.info(f"Удалён API ключ для пользователя {user_id}, провайдер: {provider}")
        return True
    
    def delete_key_by_id(self, user_id: int, key_id: int) -> bool:
        """
        Удаляет ключ по ID (только если принадлежит пользователю).
        
        Args:
            user_id: ID пользователя
            key_id: ID ключа
        
        Returns:
            bool: True если удаление успешно
        """
        key = self.db_session.query(APIKey).filter(
            APIKey.id == key_id,
            APIKey.user_id == user_id
        ).first()
        
        if not key:
            return False
        
        provider = key.provider
        self.db_session.delete(key)
        self.db_session.commit()
        
        logger.info(f"Удалён API ключ ID={key_id} для пользователя {user_id}, провайдер: {provider}")
        return True
    
    def has_key(self, user_id: int, provider: str) -> bool:
        """
        Проверяет наличие ключа для провайдера (личный или общий).
        
        Args:
            user_id: ID пользователя
            provider: Провайдер
        
        Returns:
            bool: True если ключ доступен
        """
        return self.get_key(user_id, provider) is not None
