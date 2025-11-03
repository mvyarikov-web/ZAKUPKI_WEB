"""
Базовый слой SQLAlchemy для работы с БД.
Содержит настройку engine, sessionmaker, DeclarativeBase и утилиты для управления сессиями.
"""

from typing import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool

from webapp.config import get_config


# Получаем конфигурацию
config = get_config()

# Создаём engine
# echo=True включает логирование SQL-запросов (для отладки)
engine = create_engine(
    config.database_url,
    echo=config.sql_echo,
    poolclass=NullPool,  # Для Alembic и простоты (в продакшене можно использовать QueuePool)
    pool_pre_ping=True,  # Проверка соединения перед использованием
)

# Создаём фабрику сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Базовый класс для всех моделей
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Зависимость для получения сессии БД (для Flask/FastAPI).
    
    Использование в Flask:
        @app.route('/example')
        def example():
            db = next(get_db())
            try:
                # ... работа с БД
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
    
    Yields:
        Session: Сессия SQLAlchemy
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    Контекстный менеджер для работы с БД.
    
    Использование:
        with get_db_context() as db:
            user = db.query(User).first()
            # ... работа с БД
            # Коммит происходит автоматически при выходе из контекста
    
    Yields:
        Session: Сессия SQLAlchemy с автоматическим commit/rollback
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Инициализация БД: создание всех таблиц.
    
    ВНИМАНИЕ: Использовать только для разработки/тестирования!
    В продакшене используйте Alembic миграции.
    
    Пример:
        from webapp.db.base import init_db
        init_db()
    """
    Base.metadata.create_all(bind=engine)


def drop_db():
    """
    Удаление всех таблиц из БД.
    
    ВНИМАНИЕ: Использовать только для разработки/тестирования!
    Все данные будут потеряны!
    
    Пример:
        from webapp.db.base import drop_db
        drop_db()
    """
    Base.metadata.drop_all(bind=engine)


# Экспорт для удобного импорта
__all__ = [
    'Base',
    'engine',
    'SessionLocal',
    'get_db',
    'get_db_context',
    'init_db',
    'drop_db',
]
