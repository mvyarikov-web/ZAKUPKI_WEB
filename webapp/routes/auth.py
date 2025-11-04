"""
Роуты для аутентификации и управления пользователями.

Эндпоинты:
- POST /auth/register - Регистрация нового пользователя
- POST /auth/login - Вход пользователя
- POST /auth/logout - Выход пользователя
- GET /auth/me - Получить информацию о текущем пользователе
- POST /auth/change-password - Изменить пароль
"""

from contextlib import contextmanager
from flask import Blueprint, request, jsonify, current_app, g, render_template
from webapp.services.auth_service import AuthService
from webapp.db.base import SessionLocal
from webapp.middleware.auth_middleware import require_auth


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login_page')
def login_page():
    """Страница входа/регистрации."""
    return render_template('login.html')


@contextmanager
def get_auth_service():
    """
    Контекстный менеджер для создания AuthService с автоматическим закрытием сессии БД.
    
    Использование:
        with get_auth_service() as auth_service:
            user, error = auth_service.register(email, password, role)
    
    Yields:
        AuthService: Настроенный сервис аутентификации
    """
    db_session = SessionLocal()
    try:
        auth_service = AuthService(
            db_session=db_session,
            jwt_secret=current_app.config['JWT_SECRET_KEY'],
            jwt_algorithm=current_app.config.get('JWT_ALGORITHM', 'HS256'),
            jwt_expiration_hours=current_app.config.get('JWT_EXPIRATION_HOURS', 24)
        )
        yield auth_service
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Регистрация нового пользователя.
    
    Request body:
        {
            "email": "user@example.com",
            "password": "password123",
            "role": "user"  // optional, default: "user"
        }
    
    Response:
        {
            "success": true,
            "user": {
                "id": 1,
                "email": "user@example.com",
                "role": "user",
                "created_at": "2025-11-04T12:00:00"
            }
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует тело запроса'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        role = data.get('role', 'user')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email и пароль обязательны'
            }), 400
        
        # Получаем IP и User-Agent для логирования сессии
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        
        with get_auth_service() as auth_service:
            user, error = auth_service.register(email, password, role)
            
            if error:
                return jsonify({
                    'success': False,
                    'error': error
                }), 400
            
            # Автоматически логиним пользователя после регистрации
            token, _, login_error = auth_service.login(email, password, ip_address, user_agent)
            
            if login_error:
                # Пользователь создан, но не смогли сгенерировать токен
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'role': user.role,
                        'created_at': user.created_at.isoformat() if user.created_at else None
                    },
                    'message': 'Пользователь создан, но произошла ошибка входа. Попробуйте войти вручную.'
                }), 201
            
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'role': user.role,
                    'created_at': user.created_at.isoformat() if user.created_at else None
                }
            }), 201
        
    except Exception as e:
        current_app.logger.exception(f"Register error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Внутренняя ошибка сервера'
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Вход пользователя.
    
    Request body:
        {
            "email": "user@example.com",
            "password": "password123"
        }
    
    Response:
        {
            "success": true,
            "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
            "user": {
                "id": 1,
                "email": "user@example.com",
                "role": "user"
            }
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует тело запроса'
            }), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email и пароль обязательны'
            }), 400
        
        # Получаем IP и User-Agent для логирования сессии
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        
        with get_auth_service() as auth_service:
            token, user, error = auth_service.login(email, password, ip_address, user_agent)
            
            if error:
                return jsonify({
                    'success': False,
                    'error': error
                }), 401
            
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'role': user.role
                }
            }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Login error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Внутренняя ошибка сервера'
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """
    Выход пользователя (инвалидация текущей сессии).
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
        {
            "success": true,
            "message": "Успешный выход"
        }
    """
    try:
        # Извлекаем токен из заголовка
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'Отсутствует токен'
            }), 401
        
        token = auth_header.split(' ')[1]
        
        with get_auth_service() as auth_service:
            success, error = auth_service.logout(token)
            
            if not success:
                return jsonify({
                    'success': False,
                    'error': error
                }), 400
            
            return jsonify({
                'success': True,
                'message': 'Успешный выход'
            }), 200
        
    except Exception as e:
        current_app.logger.error(f"Logout error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Внутренняя ошибка сервера'
        }), 500


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """
    Получить информацию о текущем пользователе.
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
        {
            "success": true,
            "user": {
                "id": 1,
                "email": "user@example.com",
                "role": "user",
                "is_active": true,
                "created_at": "2025-11-04T12:00:00"
            }
        }
    """
    try:
        user = g.user  # Установлен middleware
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Get current user error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Внутренняя ошибка сервера'
        }), 500


@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    """
    Изменить пароль текущего пользователя.
    
    Headers:
        Authorization: Bearer <token>
    
    Request body:
        {
            "old_password": "old_password123",
            "new_password": "new_password456"
        }
    
    Response:
        {
            "success": true,
            "message": "Пароль успешно изменён"
        }
    
    Note:
        После смены пароля все сессии пользователя инвалидируются.
        Требуется повторный вход.
    """
    try:
        user = g.user
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует тело запроса'
            }), 400
        
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not old_password or not new_password:
            return jsonify({
                'success': False,
                'error': 'Старый и новый пароли обязательны'
            }), 400
        
        with get_auth_service() as auth_service:
            success, error = auth_service.change_password(user.id, old_password, new_password)
            
            if not success:
                return jsonify({
                    'success': False,
                    'error': error
                }), 400
            
            return jsonify({
                'success': True,
                'message': 'Пароль успешно изменён. Все сессии инвалидированы. Требуется повторный вход.'
            }), 200
        
    except Exception as e:
        current_app.logger.error(f"Change password error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Внутренняя ошибка сервера'
        }), 500
