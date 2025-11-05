"""
Auth Middleware для извлечения и валидации JWT токенов.

Автоматически проверяет JWT токен в заголовке Authorization
и устанавливает g.user для текущего пользователя.
"""

from functools import wraps
from flask import request, g, jsonify, current_app

from webapp.auth.jwt_manager import extract_token_from_header
from webapp.services.auth_service import AuthService
from webapp.db.base import SessionLocal


def setup_auth_middleware(app):
    """
    Настраивает auth middleware для Flask приложения.
    
    Args:
        app: Flask приложение
        
    Note:
        Вызывается в webapp/__init__.py при инициализации приложения
    """
    
    @app.before_request
    def authenticate_request():
        """
        Выполняется перед каждым запросом.
        Извлекает JWT токен и устанавливает g.user если токен валидный.
        """
        # Сбрасываем g.user
        g.user = None
        g.auth_error = None
        
        # Извлекаем токен из заголовка Authorization
        auth_header = request.headers.get('Authorization')
        token = extract_token_from_header(auth_header)
        
        # Если токена нет в заголовке, проверяем query параметр
        if not token:
            token = request.args.get('token')
        
        if not token:
            # Токен отсутствует - это нормально для публичных эндпоинтов
            return None
        
        # Валидируем токен через AuthService
        db_session = SessionLocal()
        try:
            auth_service = AuthService(
                db_session=db_session,
                jwt_secret=current_app.config['JWT_SECRET_KEY'],
                jwt_algorithm=current_app.config.get('JWT_ALGORITHM', 'HS256'),
                jwt_expiration_hours=current_app.config.get('JWT_EXPIRATION_HOURS', 24)
            )
            
            payload, user, error = auth_service.validate_token(token)
            
            if error:
                g.auth_error = error
                # Не возвращаем ошибку здесь - пусть эндпоинт решит, требовать ли аутентификацию
                return None
            
            # Успешная валидация - устанавливаем пользователя
            g.user = user
            g.token_payload = payload
            
        except Exception as e:
            g.auth_error = f'Ошибка при валидации токена: {str(e)}'
            # Логируем ошибку, но не падаем
            if current_app.logger:
                current_app.logger.exception(f"Auth middleware error: {str(e)}")
        finally:
            # ВАЖНО: всегда закрываем сессию БД
            db_session.close()
        
        return None


def require_auth(f):
    """
    Декоратор для защиты эндпоинтов, требующих аутентификации.
    
    Использование:
        @app.route('/protected')
        @require_auth
        def protected_endpoint():
            user = g.user  # Гарантированно присутствует
            return {'message': f'Hello, {user.email}'}
    
    Args:
        f: Функция-обработчик эндпоинта
        
    Returns:
        Обёрнутая функция с проверкой аутентификации
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            error_message = g.auth_error or 'Требуется аутентификация'
            return jsonify({
                'success': False,
                'error': error_message
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_role(*allowed_roles):
    """
    Декоратор для защиты эндпоинтов с проверкой роли.
    
    Использование:
        @app.route('/admin')
        @require_role('admin')
        def admin_endpoint():
            return {'message': 'Admin panel'}
    
    Args:
        *allowed_roles: Список разрешённых ролей (например, 'admin', 'user')
        
    Returns:
        Декоратор функции
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Сначала проверяем аутентификацию
            if g.user is None:
                error_message = g.auth_error or 'Требуется аутентификация'
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 401
            
            # Затем проверяем роль
            if g.user.role not in allowed_roles:
                return jsonify({
                    'success': False,
                    'error': 'Недостаточно прав доступа'
                }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def get_current_user():
    """
    Получить текущего аутентифицированного пользователя.
    
    Returns:
        User или None, если пользователь не аутентифицирован
        
    Example:
        user = get_current_user()
        if user:
            print(f"Current user: {user.email}")
    """
    return getattr(g, 'user', None)


def is_authenticated() -> bool:
    """
    Проверить, аутентифицирован ли текущий пользователь.
    
    Returns:
        True если пользователь аутентифицирован, False иначе
    """
    return g.user is not None
