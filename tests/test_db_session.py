"""
Тесты базового слоя SQLAlchemy.
Проверяет создание engine, sessionmaker, Base и утилиты управления сессиями.
"""

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String


class TestDatabaseBase:
    """Тесты базового слоя БД."""
    
    def test_base_import(self):
        """Base импортируется корректно."""
        from webapp.db import Base
        
        assert Base is not None
        assert hasattr(Base, 'metadata')
    
    def test_engine_import(self):
        """Engine импортируется корректно."""
        from webapp.db import engine
        
        assert engine is not None
        assert hasattr(engine, 'url')
    
    def test_session_local_import(self):
        """SessionLocal импортируется корректно."""
        from webapp.db import SessionLocal
        
        assert SessionLocal is not None
        assert callable(SessionLocal)
    
    def test_get_db_import(self):
        """get_db импортируется корректно."""
        from webapp.db import get_db
        
        assert get_db is not None
        assert callable(get_db)
    
    def test_get_db_context_import(self):
        """get_db_context импортируется корректно."""
        from webapp.db import get_db_context
        
        assert get_db_context is not None
        assert callable(get_db_context)
    
    def test_base_can_create_model(self, monkeypatch):
        """Base может быть использован для создания модели."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        from webapp.db import Base
        
        # Создаём тестовую модель
        class TestModel(Base):
            __tablename__ = 'test_table'
            id = Column(Integer, primary_key=True)
            name = Column(String(50))
        
        # Проверяем, что модель создана корректно
        assert TestModel.__tablename__ == 'test_table'
        assert hasattr(TestModel, 'id')
        assert hasattr(TestModel, 'name')
    
    def test_session_local_creates_session(self, monkeypatch):
        """SessionLocal создаёт экземпляр Session."""
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        # Пересоздаём модуль с новыми настройками
        import importlib
        import webapp.db.base
        importlib.reload(webapp.db.base)
        
        from webapp.db.base import SessionLocal
        
        db = SessionLocal()
        
        assert isinstance(db, Session)
        db.close()
    
    def test_get_db_generator(self, monkeypatch):
        """get_db является генератором и возвращает Session."""
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        # Пересоздаём модуль
        import importlib
        import webapp.db.base
        importlib.reload(webapp.db.base)
        
        from webapp.db.base import get_db
        
        gen = get_db()
        db = next(gen)
        
        assert isinstance(db, Session)
        
        # Закрываем генератор
        try:
            next(gen)
        except StopIteration:
            pass
    
    def test_get_db_context_manager(self, monkeypatch):
        """get_db_context работает как контекстный менеджер."""
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        # Пересоздаём модуль
        import importlib
        import webapp.db.base
        importlib.reload(webapp.db.base)
        
        from webapp.db.base import get_db_context
        
        with get_db_context() as db:
            assert isinstance(db, Session)
    
    def test_init_drop_db_functions(self, monkeypatch):
        """init_db и drop_db импортируются корректно."""
        from webapp.db import init_db, drop_db
        
        assert callable(init_db)
        assert callable(drop_db)
    
    def test_engine_url_from_config(self, monkeypatch):
        """Engine использует URL из конфигурации."""
        test_url = 'postgresql://test_user:test_pass@test_host:5432/test_db'
        monkeypatch.setenv('DATABASE_URL', test_url)
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        # Пересоздаём модуль
        import importlib
        import webapp.db.base
        importlib.reload(webapp.db.base)
        
        from webapp.db.base import engine
        
        # Проверяем, что URL соответствует конфигурации
        engine_url = str(engine.url)
        assert 'test_user' in engine_url or 'test_host' in engine_url or 'test_db' in engine_url


def test_base_metadata_accessible():
    """Base.metadata доступен для Alembic."""
    from webapp.db import Base
    
    assert hasattr(Base, 'metadata')
    assert Base.metadata is not None


def test_all_exports():
    """Все необходимые символы экспортируются из webapp.db."""
    from webapp import db
    
    required_exports = [
        'Base',
        'engine',
        'SessionLocal',
        'get_db',
        'get_db_context',
        'init_db',
        'drop_db',
    ]
    
    for export in required_exports:
        assert hasattr(db, export), f"Отсутствует экспорт: {export}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
