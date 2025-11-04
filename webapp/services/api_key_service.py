"""
Сервис для шифрования/расшифровки API ключей.

Использует Fernet (симметричное шифрование) для защиты ключей в БД.
"""

from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


class ApiKeyService:
    """
    Сервис для работы с шифрованием API ключей.
    
    Использует Fernet для симметричного шифрования ключей перед сохранением в БД.
    """
    
    def __init__(self, encryption_key: bytes):
        """
        Инициализация сервиса шифрования.
        
        Args:
            encryption_key: Ключ Fernet (32 байта base64-encoded)
            
        Raises:
            ValueError: Если ключ некорректен
            
        Example:
            >>> from webapp.config import get_config
            >>> config = get_config()
            >>> service = ApiKeyService(config.fernet_key)
        """
        try:
            self.cipher = Fernet(encryption_key)
        except Exception as e:
            raise ValueError(f"Некорректный ключ шифрования: {str(e)}")
    
    def encrypt_key(self, plain_key: str) -> str:
        """
        Зашифровать API ключ.
        
        Args:
            plain_key: Открытый API ключ
            
        Returns:
            Зашифрованный ключ (base64 строка)
            
        Example:
            >>> encrypted = service.encrypt_key('sk-proj-abc123...')
            >>> print(encrypted[:20])  # gAAAABl...
        """
        if not plain_key:
            raise ValueError("API ключ не может быть пустым")
        
        encrypted_bytes = self.cipher.encrypt(plain_key.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    
    def decrypt_key(self, encrypted_key: str) -> Optional[str]:
        """
        Расшифровать API ключ.
        
        Args:
            encrypted_key: Зашифрованный ключ
            
        Returns:
            Расшифрованный ключ или None при ошибке
            
        Example:
            >>> decrypted = service.decrypt_key('gAAAABl...')
            >>> if decrypted:
            ...     print(f"Key starts with: {decrypted[:10]}")
        """
        if not encrypted_key:
            return None
        
        try:
            decrypted_bytes = self.cipher.decrypt(encrypted_key.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except InvalidToken:
            # Ключ был зашифрован другим ключом или повреждён
            return None
        except Exception:
            return None
    
    @staticmethod
    def mask_key(key: str, visible_chars: int = 4) -> str:
        """
        Замаскировать ключ для отображения в UI.
        
        Показывает только последние N символов, остальное заменяет на '*'.
        
        Args:
            key: Открытый ключ
            visible_chars: Сколько символов показывать в конце
            
        Returns:
            Замаскированный ключ
            
        Example:
            >>> masked = ApiKeyService.mask_key('sk-proj-abc123def456', visible_chars=4)
            >>> print(masked)  # ********f456
        """
        if not key:
            return ""
        
        if len(key) <= visible_chars:
            return key
        
        mask_length = len(key) - visible_chars
        return '*' * mask_length + key[-visible_chars:]
    
    @staticmethod
    def validate_key_format(key: str, provider: str) -> tuple[bool, Optional[str]]:
        """
        Базовая валидация формата API ключа для провайдера.
        
        Args:
            key: API ключ
            provider: Название провайдера (openai, anthropic, deepseek, etc.)
            
        Returns:
            (is_valid: bool, error_message: Optional[str])
            
        Example:
            >>> valid, error = ApiKeyService.validate_key_format('sk-proj-abc', 'openai')
            >>> if not valid:
            ...     print(f"Invalid: {error}")
        """
        if not key or not key.strip():
            return False, "API ключ не может быть пустым"
        
        key = key.strip()
        
        # Базовые проверки по провайдерам
        if provider == 'openai':
            if not key.startswith(('sk-', 'sk-proj-')):
                return False, "OpenAI ключ должен начинаться с 'sk-' или 'sk-proj-'"
            if len(key) < 20:
                return False, "OpenAI ключ слишком короткий"
        
        elif provider == 'anthropic':
            if not key.startswith('sk-ant-'):
                return False, "Anthropic ключ должен начинаться с 'sk-ant-'"
            if len(key) < 30:
                return False, "Anthropic ключ слишком короткий"
        
        elif provider == 'deepseek':
            if len(key) < 10:
                return False, "DeepSeek ключ слишком короткий"
        
        elif provider == 'perplexity':
            if not key.startswith('pplx-'):
                return False, "Perplexity ключ должен начинаться с 'pplx-'"
            if len(key) < 20:
                return False, "Perplexity ключ слишком короткий"
        
        else:
            # Для неизвестных провайдеров просто проверяем длину
            if len(key) < 10:
                return False, f"Ключ для {provider} слишком короткий (минимум 10 символов)"
        
        return True, None
    
    def encrypt_and_validate(
        self,
        plain_key: str,
        provider: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Валидация и шифрование ключа.
        
        Args:
            plain_key: Открытый API ключ
            provider: Название провайдера
            
        Returns:
            (encrypted_key: Optional[str], error: Optional[str])
            Если успешно: (encrypted_key, None)
            Если ошибка: (None, error_message)
            
        Example:
            >>> encrypted, error = service.encrypt_and_validate('sk-proj-abc', 'openai')
            >>> if error:
            ...     print(f"Error: {error}")
            ... else:
            ...     print(f"Encrypted: {encrypted[:20]}")
        """
        # Валидация формата
        is_valid, error = self.validate_key_format(plain_key, provider)
        if not is_valid:
            return None, error
        
        # Шифрование
        try:
            encrypted = self.encrypt_key(plain_key.strip())
            return encrypted, None
        except Exception as e:
            return None, f"Ошибка при шифровании: {str(e)}"
