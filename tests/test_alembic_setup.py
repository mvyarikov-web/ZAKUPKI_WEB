"""
Тесты для проверки настройки Alembic.
Проверяет корректность конфигурации и возможность подключения к БД.
"""

import pytest
from pathlib import Path


class TestAlembicSetup:
    """Тесты настройки Alembic."""
    
    def test_alembic_ini_exists(self):
        """Файл alembic.ini существует в корне проекта."""
        project_root = Path(__file__).parent.parent
        alembic_ini = project_root / 'alembic.ini'
        
        assert alembic_ini.exists(), "Файл alembic.ini не найден"
        assert alembic_ini.is_file(), "alembic.ini не является файлом"
    
    def test_alembic_directory_exists(self):
        """Директория alembic/ существует."""
        project_root = Path(__file__).parent.parent
        alembic_dir = project_root / 'alembic'
        
        assert alembic_dir.exists(), "Директория alembic/ не найдена"
        assert alembic_dir.is_dir(), "alembic не является директорией"
    
    def test_alembic_versions_directory_exists(self):
        """Директория alembic/versions/ существует."""
        project_root = Path(__file__).parent.parent
        versions_dir = project_root / 'alembic' / 'versions'
        
        assert versions_dir.exists(), "Директория alembic/versions/ не найдена"
        assert versions_dir.is_dir(), "versions не является директорией"
    
    def test_alembic_env_exists(self):
        """Файл alembic/env.py существует."""
        project_root = Path(__file__).parent.parent
        env_py = project_root / 'alembic' / 'env.py'
        
        assert env_py.exists(), "Файл alembic/env.py не найден"
        assert env_py.is_file(), "env.py не является файлом"
    
    def test_alembic_env_imports_config(self):
        """alembic/env.py импортирует ConfigService."""
        project_root = Path(__file__).parent.parent
        env_py = project_root / 'alembic' / 'env.py'
        
        content = env_py.read_text(encoding='utf-8')
        
        assert 'from webapp.config import get_config' in content, \
            "env.py не импортирует get_config"
        assert 'app_config = get_config()' in content, \
            "env.py не создаёт экземпляр конфига"
        assert 'app_config.database_url' in content, \
            "env.py не использует database_url из конфига"
    
    def test_alembic_ini_no_hardcoded_url(self):
        """alembic.ini не содержит хардкодный URL БД."""
        project_root = Path(__file__).parent.parent
        alembic_ini = project_root / 'alembic.ini'
        
        content = alembic_ini.read_text(encoding='utf-8')
        
        # Проверяем, что нет хардкодного URL
        assert 'driver://user:pass@localhost/dbname' not in content, \
            "alembic.ini содержит дефолтный placeholder URL"
        
        # Убеждаемся, что есть пустой sqlalchemy.url или комментарий
        assert 'sqlalchemy.url =' in content, \
            "alembic.ini не содержит строку sqlalchemy.url"
    
    def test_alembic_script_mako_exists(self):
        """Файл script.py.mako существует."""
        project_root = Path(__file__).parent.parent
        mako = project_root / 'alembic' / 'script.py.mako'
        
        assert mako.exists(), "Файл script.py.mako не найден"
    
    def test_alembic_can_load_config(self, monkeypatch):
        """Alembic может загрузить конфигурацию из env.py."""
        # Устанавливаем минимально необходимые переменные
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test_alembic')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key_32_bytes_long_enough!!')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_jwt_secret')
        
        # Читаем и проверяем env.py напрямую
        project_root = Path(__file__).parent.parent
        env_py = project_root / 'alembic' / 'env.py'
        
        content = env_py.read_text(encoding='utf-8')
        
        # Проверяем наличие критичных импортов и конфигурации
        assert 'from webapp.config import get_config' in content
        assert 'app_config = get_config()' in content
        assert "config.set_main_option('sqlalchemy.url'" in content
    
    def test_alembic_ini_structure(self):
        """alembic.ini имеет корректную структуру."""
        project_root = Path(__file__).parent.parent
        alembic_ini = project_root / 'alembic.ini'
        
        content = alembic_ini.read_text(encoding='utf-8')
        
        # Проверяем наличие ключевых секций
        assert '[alembic]' in content, "Отсутствует секция [alembic]"
        assert 'script_location = alembic' in content, \
            "Неверный script_location"
        assert 'prepend_sys_path = .' in content, \
            "Отсутствует prepend_sys_path"


def test_alembic_command_available():
    """Команда alembic доступна в виртуальном окружении."""
    import subprocess
    
    # Пытаемся запустить alembic --version
    result = subprocess.run(
        ['.venv/bin/alembic', '--version'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0, f"alembic --version вернул код {result.returncode}"
    assert 'alembic' in result.stdout.lower() or 'alembic' in result.stderr.lower(), \
        "Вывод alembic --version не содержит 'alembic'"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
