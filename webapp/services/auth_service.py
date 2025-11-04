"""
Сервис аутентификации и авторизации пользователей.

Управляет регистрацией, входом, выходом и валидацией пользователей.
Использует bcrypt для хеширования паролей и JWT для токенов.
"""

import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from webapp.auth.jwt_manager import generate_token, verify_token, hash_token
from webapp.db.repositories import UserRepository, SessionRepository
from webapp.db.models import User, UserRole


class AuthService:
    """Сервис для аутентификации и управления пользовательскими сессиями."""
    
    def __init__(
        self,
        db_session: Session,
        jwt_secret: str,
        jwt_algorithm: str = 'HS256',
        jwt_expiration_hours: int = 24
    ):
        """
        Инициализация сервиса аутентификации.
        
        Args:
            db_session: SQLAlchemy сессия для работы с БД
            jwt_secret: Секретный ключ для JWT токенов
            jwt_algorithm: Алгоритм подписи JWT (по умолчанию HS256)
            jwt_expiration_hours: Время жизни JWT токена в часах
        """
        self.db_session = db_session
        self.user_repo = UserRepository(db_session)
        self.session_repo = SessionRepository(db_session)
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiration_hours = jwt_expiration_hours
    
    @staticmethod
    def hash_password(plain_password: str) -> str:
        """
        Хеширует пароль с использованием bcrypt.
        
        Args:
            plain_password: Пароль в открытом виде
            
        Returns:
            Хешированный пароль (строка)
            
        Example:
            >>> hashed = AuthService.hash_password('my_secret_password')
            >>> print(hashed)
            '$2b$12$...'
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def validate_password(plain_password: str, hashed_password: str) -> bool:
        """
        Проверяет соответствие пароля хешу.
        
        Args:
            plain_password: Пароль в открытом виде
            hashed_password: Хешированный пароль из БД
            
        Returns:
            True если пароль совпадает, False иначе
            
        Example:
            >>> is_valid = AuthService.validate_password('my_secret_password', hashed)
            >>> if is_valid:
            ...     print("Password correct!")
        """
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception:
            return False
    
    def register(
        self,
        email: str,
        password: str,
        role: str = 'user'
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        Регистрирует нового пользователя.
        
        Args:
            email: Email пользователя (уникальный)
            password: Пароль в открытом виде
            role: Роль пользователя (по умолчанию 'user')
            
        Returns:
            Кортеж (пользователь, сообщение об ошибке)
            Если успешно: (User, None)
            Если ошибка: (None, 'error message')
            
        Example:
            >>> user, error = auth_service.register('user@example.com', 'password123')
            >>> if error:
            ...     print(f"Registration failed: {error}")
            ... else:
            ...     print(f"User registered: {user.email}")
        """
        # Проверка существования пользователя
        existing_user = self.user_repo.get_by_email(email)
        if existing_user:
            return None, 'Пользователь с таким email уже существует'
        
        # Валидация email
        if '@' not in email or '.' not in email:
            return None, 'Некорректный формат email'
        
        # Валидация пароля
        if len(password) < 6:
            return None, 'Пароль должен содержать минимум 6 символов'
        
        # Хеширование пароля
        password_hash = self.hash_password(password)
        
        # Преобразование строки роли в enum
        try:
            user_role = UserRole(role.lower())
        except ValueError:
            return None, f'Неверная роль: {role}. Допустимые: user, admin'
        
        # Создание пользователя
        try:
            user = self.user_repo.create_user(
                email=email,
                password_hash=password_hash,
                role=user_role
            )
            return user, None
        except Exception as e:
            return None, f'Ошибка при создании пользователя: {str(e)}'
    
    def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[User], Optional[str]]:
        """
        Выполняет вход пользователя и создаёт JWT токен.
        
        Args:
            email: Email пользователя
            password: Пароль в открытом виде
            ip_address: IP адрес клиента (опционально)
            user_agent: User-Agent браузера (опционально)
            
        Returns:
            Кортеж (токен, пользователь, ошибка)
            Если успешно: ('jwt_token', User, None)
            Если ошибка: (None, None, 'error message')
            
        Example:
            >>> token, user, error = auth_service.login('user@example.com', 'password123')
            >>> if error:
            ...     print(f"Login failed: {error}")
            ... else:
            ...     print(f"Token: {token}")
        """
        # Поиск пользователя
        user = self.user_repo.get_by_email(email)
        if not user:
            return None, None, 'Неверный email или пароль'
        
        # Проверка пароля
        if not self.validate_password(password, user.password_hash):
            return None, None, 'Неверный email или пароль'
        
        # Генерация JWT токена
        token = generate_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            jwt_secret=self.jwt_secret,
            jwt_algorithm=self.jwt_algorithm,
            expiration_hours=self.jwt_expiration_hours
        )
        
        # Сохранение сессии в БД
        token_hash_value = hash_token(token)
        expires_at = datetime.utcnow() + timedelta(hours=self.jwt_expiration_hours)
        
        try:
            self.session_repo.create_session(
                user_id=user.id,
                token_hash=token_hash_value,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent
            )
        except Exception as e:
            return None, None, f'Ошибка при создании сессии: {str(e)}'
        
        return token, user, None
    
    def logout(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Выполняет выход пользователя (инвалидация токена).
        
        Args:
            token: JWT токен
            
        Returns:
            Кортеж (успех, ошибка)
            Если успешно: (True, None)
            Если ошибка: (False, 'error message')
            
        Example:
            >>> success, error = auth_service.logout(token)
            >>> if success:
            ...     print("Logged out successfully")
        """
        token_hash_value = hash_token(token)
        success = self.session_repo.invalidate_session(token_hash_value)
        
        if success:
            return True, None
        else:
            return False, 'Сессия не найдена или уже неактивна'
    
    def validate_token(self, token: str) -> Tuple[Optional[dict], Optional[User], Optional[str]]:
        """
        Валидирует JWT токен и возвращает данные пользователя.
        
        Args:
            token: JWT токен
            
        Returns:
            Кортеж (payload, пользователь, ошибка)
            Если успешно: (payload_dict, User, None)
            Если ошибка: (None, None, 'error message')
            
        Example:
            >>> payload, user, error = auth_service.validate_token(token)
            >>> if error:
            ...     print(f"Invalid token: {error}")
            ... else:
            ...     print(f"Authenticated as: {user.email}")
        """
        # Проверка JWT подписи и срока действия
        payload = verify_token(token, self.jwt_secret, self.jwt_algorithm)
        if not payload:
            return None, None, 'Невалидный или истёкший токен'
        
        # Проверка сессии в БД
        token_hash_value = hash_token(token)
        session_obj = self.session_repo.get_active_by_token_hash(token_hash_value)
        
        if not session_obj:
            return None, None, 'Сессия не найдена или неактивна'
        
        # Получение пользователя
        user = self.user_repo.get_by_id(payload['user_id'])
        if not user:
            return None, None, 'Пользователь не найден'
        
        return payload, user, None
    
    def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Изменяет пароль пользователя.
        
        Args:
            user_id: ID пользователя
            old_password: Старый пароль
            new_password: Новый пароль
            
        Returns:
            Кортеж (успех, ошибка)
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False, 'Пользователь не найден'
        
        # Проверка старого пароля
        if not self.validate_password(old_password, user.password_hash):
            return False, 'Неверный текущий пароль'
        
        # Валидация нового пароля
        if len(new_password) < 6:
            return False, 'Новый пароль должен содержать минимум 6 символов'
        
        # Хеширование и обновление
        new_password_hash = self.hash_password(new_password)
        success = self.user_repo.update_password(user_id, new_password_hash)
        
        if success:
            # Инвалидация всех сессий пользователя (требуется повторный вход)
            self.session_repo.invalidate_all_user_sessions(user_id)
            return True, None
        else:
            return False, 'Ошибка при обновлении пароля'
