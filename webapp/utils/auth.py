"""
Утилиты для работы с JWT токенами и аутентификацией.
"""
import jwt
import datetime
from functools import wraps
from flask import request, jsonify, g, current_app
from webapp.db.models import User
from webapp.db.session import get_session


def generate_token(user_id: int, email: str) -> str:
    """
    Генерирует JWT токен для пользователя.
    
    Args:
        user_id: ID пользователя
        email: Email пользователя
        
    Returns:
        JWT токен
    """
    config = current_app.config
    expiration = datetime.datetime.utcnow() + datetime.timedelta(
        hours=config.get('JWT_EXPIRATION_HOURS', 24)
    )
    
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': expiration,
        'iat': datetime.datetime.utcnow()
    }
    
    token = jwt.encode(
        payload,
        config['JWT_SECRET_KEY'],
        algorithm=config.get('JWT_ALGORITHM', 'HS256')
    )
    
    return token


def decode_token(token: str) -> dict:
    """
    Декодирует и валидирует JWT токен.
    
    Args:
        token: JWT токен
        
    Returns:
        Payload токена
        
    Raises:
        jwt.ExpiredSignatureError: Токен истёк
        jwt.InvalidTokenError: Токен невалиден
    """
    config = current_app.config
    payload = jwt.decode(
        token,
        config['JWT_SECRET_KEY'],
        algorithms=[config.get('JWT_ALGORITHM', 'HS256')]
    )
    return payload


def get_current_user():
    """
    Получить текущего авторизованного пользователя из контекста запроса.
    
    Returns:
        User object или None
    """
    return getattr(g, 'current_user', None)


def require_auth(f):
    """
    Декоратор для защиты роутов. Требует валидный JWT токен.
    Устанавливает g.current_user для использования в обработчике.
    
    Usage:
        @app.route('/protected')
        @require_auth
        def protected_route():
            user = get_current_user()
            return {'message': f'Hello, {user.email}'}
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Получаем токен из заголовка Authorization
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        # Проверяем формат "Bearer <token>"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Неверный формат токена'}), 401
        
        token = parts[1]
        
        try:
            # Декодируем токен
            payload = decode_token(token)
            user_id = payload['user_id']
            
            # Загружаем пользователя из БД
            session = get_session()
            try:
                user = session.query(User).filter(User.id == user_id).first()
                
                if not user:
                    return jsonify({'error': 'Пользователь не найден'}), 401
                
                # Сохраняем пользователя в контексте запроса
                g.current_user = user
                
            finally:
                session.close()
            
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Токен истёк'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Невалидный токен'}), 401
        except Exception as e:
            current_app.logger.error(f'Auth error: {e}')
            return jsonify({'error': 'Ошибка авторизации'}), 401
    
    return decorated_function


def optional_auth(f):
    """
    Декоратор для роутов с опциональной авторизацией.
    Если токен предоставлен и валиден, устанавливает g.current_user.
    Если токена нет или он невалиден, продолжает без авторизации.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
                try:
                    payload = decode_token(token)
                    user_id = payload['user_id']
                    
                    session = get_session()
                    try:
                        user = session.query(User).filter(User.id == user_id).first()
                        if user:
                            g.current_user = user
                    finally:
                        session.close()
                except:
                    pass  # Игнорируем ошибки, продолжаем без авторизации
        
        return f(*args, **kwargs)
    
    return decorated_function
