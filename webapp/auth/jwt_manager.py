"""
JWT Token Manager для аутентификации пользователей.

Использует PyJWT для создания и проверки JWT токенов.
"""

import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import hashlib


def generate_token(
    user_id: int,
    email: str,
    role: str,
    jwt_secret: str,
    jwt_algorithm: str = 'HS256',
    expiration_hours: int = 24
) -> str:
    """
    Генерирует JWT токен для пользователя.
    
    Args:
        user_id: ID пользователя
        email: Email пользователя
        role: Роль пользователя (admin, user)
        jwt_secret: Секретный ключ для подписи JWT
        jwt_algorithm: Алгоритм подписи (по умолчанию HS256)
        expiration_hours: Время жизни токена в часах
        
    Returns:
        Закодированный JWT токен (строка)
        
    Example:
        >>> token = generate_token(1, 'user@example.com', 'user', 'secret')
        >>> print(token)
        'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
    """
    now = datetime.utcnow()
    expiration = now + timedelta(hours=expiration_hours)
    
    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'iat': now,  # issued at
        'exp': expiration  # expires at
    }
    
    token = jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)
    return token


def verify_token(token: str, jwt_secret: str, jwt_algorithm: str = 'HS256') -> Optional[Dict[str, Any]]:
    """
    Проверяет и декодирует JWT токен.
    
    Args:
        token: JWT токен для проверки
        jwt_secret: Секретный ключ для проверки подписи
        jwt_algorithm: Алгоритм подписи
        
    Returns:
        Payload токена (dict) если валидный, None если невалидный или истёк
        
    Example:
        >>> payload = verify_token(token, 'secret')
        >>> if payload:
        ...     print(f"User ID: {payload['user_id']}")
    """
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        # Токен истёк
        return None
    except jwt.InvalidTokenError:
        # Токен невалидный (неправильная подпись, формат и т.д.)
        return None


def decode_token(token: str, verify: bool = False) -> Optional[Dict[str, Any]]:
    """
    Декодирует JWT токен без проверки подписи (для отладки).
    
    Args:
        token: JWT токен
        verify: Проверять ли подпись (по умолчанию False)
        
    Returns:
        Payload токена (dict) или None при ошибке
        
    Warning:
        Используйте только для отладки! В продакшене используйте verify_token()
    """
    try:
        options = {'verify_signature': verify}
        payload = jwt.decode(token, options=options, algorithms=['HS256'])
        return payload
    except Exception:
        return None


def hash_token(token: str) -> str:
    """
    Создаёт SHA-256 хеш токена для хранения в БД.
    
    Args:
        token: JWT токен
        
    Returns:
        Hex-строка хеша токена
        
    Note:
        В БД хранится хеш токена, а не сам токен (для безопасности)
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def extract_token_from_header(authorization_header: Optional[str]) -> Optional[str]:
    """
    Извлекает JWT токен из HTTP заголовка Authorization.
    
    Args:
        authorization_header: Значение заголовка Authorization
        
    Returns:
        JWT токен или None, если заголовок отсутствует или неверного формата
        
    Example:
        >>> header = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        >>> token = extract_token_from_header(header)
    """
    if not authorization_header:
        return None
    
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    
    return parts[1]
