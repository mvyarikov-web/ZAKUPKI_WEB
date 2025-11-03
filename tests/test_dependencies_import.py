"""
Тест импорта новых зависимостей для инкремента 13.
Проверяет, что все критичные модули установлены корректно.
"""

import pytest


def test_sqlalchemy_import():
    """Проверка импорта SQLAlchemy 2.0+."""
    import sqlalchemy
    from sqlalchemy import __version__
    
    # SQLAlchemy 2.0.x
    major, minor = map(int, __version__.split('.')[:2])
    assert major == 2 and minor >= 0, f"Требуется SQLAlchemy 2.0+, установлена {__version__}"


def test_alembic_import():
    """Проверка импорта Alembic."""
    import alembic
    from alembic import __version__
    
    # Alembic 1.13.x
    major, minor = map(int, __version__.split('.')[:2])
    assert major == 1 and minor >= 13, f"Требуется Alembic 1.13+, установлена {__version__}"


def test_cryptography_import():
    """Проверка импорта cryptography (для Fernet)."""
    from cryptography.fernet import Fernet
    
    # Генерация тестового ключа
    key = Fernet.generate_key()
    cipher = Fernet(key)
    
    # Тест шифрования/расшифровки
    plaintext = "тестовый ключ API"
    ciphertext = cipher.encrypt(plaintext.encode())
    decrypted = cipher.decrypt(ciphertext).decode()
    
    assert decrypted == plaintext, "Fernet шифрование/расшифровка не работает"


def test_bcrypt_import():
    """Проверка импорта bcrypt (для паролей)."""
    import bcrypt
    
    # Тест хеширования пароля
    password = "test_password_123"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
    
    # Проверка валидации
    assert bcrypt.checkpw(password.encode(), hashed), "bcrypt проверка пароля не работает"
    assert not bcrypt.checkpw("wrong_password".encode(), hashed), "bcrypt пропустил неверный пароль"


def test_pyjwt_import():
    """Проверка импорта PyJWT."""
    import jwt
    
    # Тест создания и валидации токена
    secret = "test_secret_key"
    payload = {"user_id": 123, "email": "test@example.com"}
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    
    assert decoded["user_id"] == 123, "JWT декодирование не работает"
    assert decoded["email"] == "test@example.com"


def test_python_dotenv_import():
    """Проверка импорта python-dotenv."""
    from dotenv import load_dotenv, find_dotenv
    
    # Проверка базового функционала
    # load_dotenv() возвращает bool, find_dotenv() — путь к файлу или ""
    assert callable(load_dotenv), "load_dotenv не является функцией"
    assert callable(find_dotenv), "find_dotenv не является функцией"


def test_all_imports_combined():
    """Комплексная проверка всех новых импортов."""
    imports = [
        "sqlalchemy",
        "alembic",
        "cryptography.fernet",
        "bcrypt",
        "jwt",
        "dotenv",
    ]
    
    for module_name in imports:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"Не удалось импортировать {module_name}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
