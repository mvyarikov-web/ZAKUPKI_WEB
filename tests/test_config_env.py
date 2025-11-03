"""
Тесты для ConfigService.
Проверяет загрузку конфигурации, валидацию, fail-fast поведение.
"""

import os
import pytest
import tempfile
from pathlib import Path
from webapp.config import ConfigService


class TestConfigService:
    """Тесты сервиса конфигурации."""
    
    def test_config_with_all_required_vars(self, monkeypatch):
        """Конфиг успешно инициализируется при наличии всех обязательных переменных."""
        # Устанавливаем минимально необходимые переменные
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@localhost/testdb')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_fernet_key_32_bytes_long!!')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_jwt_secret_key')
        
        config = ConfigService()
        
        assert config.database_url == 'postgresql://user:pass@localhost/testdb'
        assert config.fernet_key == b'test_fernet_key_32_bytes_long!!'
        assert config.jwt_secret == 'test_jwt_secret_key'
    
    def test_config_fails_without_database_url(self, monkeypatch):
        """Конфиг падает при отсутствии DATABASE_URL."""
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        monkeypatch.delenv('DATABASE_URL', raising=False)
        
        with pytest.raises(RuntimeError) as exc_info:
            ConfigService()
        
        assert 'DATABASE_URL' in str(exc_info.value)
        assert 'КРИТИЧЕСКАЯ ОШИБКА' in str(exc_info.value)
    
    def test_config_fails_without_fernet_key(self, monkeypatch):
        """Конфиг падает при отсутствии FERNET_ENCRYPTION_KEY."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        monkeypatch.delenv('FERNET_ENCRYPTION_KEY', raising=False)
        
        with pytest.raises(RuntimeError) as exc_info:
            ConfigService()
        
        assert 'FERNET_ENCRYPTION_KEY' in str(exc_info.value)
    
    def test_config_fails_without_jwt_secret(self, monkeypatch):
        """Конфиг падает при отсутствии JWT_SECRET_KEY."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.delenv('JWT_SECRET_KEY', raising=False)
        
        with pytest.raises(RuntimeError) as exc_info:
            ConfigService()
        
        assert 'JWT_SECRET_KEY' in str(exc_info.value)
    
    def test_config_fails_with_empty_values(self, monkeypatch):
        """Конфиг падает при пустых значениях обязательных переменных."""
        monkeypatch.setenv('DATABASE_URL', '   ')  # Только пробелы
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', '')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        with pytest.raises(RuntimeError) as exc_info:
            ConfigService()
        
        error_msg = str(exc_info.value)
        assert 'DATABASE_URL' in error_msg
        assert 'FERNET_ENCRYPTION_KEY' in error_msg
    
    def test_config_default_values(self, monkeypatch):
        """Опциональные параметры имеют корректные дефолтные значения."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        
        config = ConfigService()
        
        # Flask настройки
        assert config.flask_env == 'development'
        assert config.flask_port == 5000
        assert config.flask_host == '127.0.0.1'
        assert config.debug_mode is False
        
        # Dual-mode
        assert config.use_database is False
        
        # Логирование
        assert config.log_level == 'INFO'
        assert config.log_to_console is True  # По умолчанию в development
        
        # Лимиты
        assert config.max_upload_size_mb == 100
        assert config.max_files_per_upload == 50
        assert config.indexing_timeout_seconds == 300
        
        # pgvector
        assert config.vector_dimension == 1536
        assert config.pgvector_lists == 100
        
        # Безопасность
        assert config.secure_cookies is False
        assert config.csrf_enabled is True
    
    def test_config_custom_values(self, monkeypatch):
        """Кастомные значения корректно переопределяют дефолты."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://prod-server/db')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'prod_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'prod_secret')
        monkeypatch.setenv('FLASK_ENV', 'production')
        monkeypatch.setenv('FLASK_PORT', '8080')
        monkeypatch.setenv('USE_DATABASE', 'true')
        monkeypatch.setenv('LOG_LEVEL', 'WARNING')
        monkeypatch.setenv('MAX_UPLOAD_SIZE_MB', '50')
        monkeypatch.setenv('VECTOR_DIMENSION', '3072')
        
        config = ConfigService()
        
        assert config.flask_env == 'production'
        assert config.flask_port == 8080
        assert config.use_database is True
        assert config.log_level == 'WARNING'
        assert config.max_upload_size_mb == 50
        assert config.max_upload_size_bytes == 50 * 1024 * 1024
        assert config.vector_dimension == 3072
    
    def test_config_loads_from_dotenv_file(self, monkeypatch):
        """Конфиг загружается из .env файла."""
        # Создаём временный .env файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('DATABASE_URL=postgresql://from_file/db\n')
            f.write('FERNET_ENCRYPTION_KEY=file_key\n')
            f.write('JWT_SECRET_KEY=file_secret\n')
            f.write('FLASK_PORT=9000\n')
            temp_env_path = f.name
        
        try:
            config = ConfigService(env_file=temp_env_path)
            
            assert config.database_url == 'postgresql://from_file/db'
            assert config.fernet_key == b'file_key'
            assert config.jwt_secret == 'file_secret'
            assert config.flask_port == 9000
        finally:
            os.unlink(temp_env_path)
    
    def test_config_get_methods(self, monkeypatch):
        """Универсальные геттеры работают корректно."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'test_key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'test_secret')
        monkeypatch.setenv('CUSTOM_VAR', 'custom_value')
        monkeypatch.setenv('CUSTOM_BOOL', 'true')
        monkeypatch.setenv('CUSTOM_INT', '42')
        
        config = ConfigService()
        
        # get()
        assert config.get('CUSTOM_VAR') == 'custom_value'
        assert config.get('NON_EXISTENT', 'default') == 'default'
        
        # get_bool()
        assert config.get_bool('CUSTOM_BOOL') is True
        assert config.get_bool('NON_EXISTENT', False) is False
        
        # get_int()
        assert config.get_int('CUSTOM_INT') == 42
        assert config.get_int('NON_EXISTENT', 99) == 99
    
    def test_config_to_dict_masks_secrets(self, monkeypatch):
        """to_dict() маскирует секретные значения."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret_password@localhost/db')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'very_secret_key_32_bytes_long!')
        monkeypatch.setenv('JWT_SECRET_KEY', 'super_secret_jwt_key')
        
        config = ConfigService()
        config_dict = config.to_dict()
        
        # Проверяем, что секреты замаскированы
        assert 'secret_password' not in config_dict['database_url']
        assert '...' in config_dict['database_url']
        
        # Проверяем, что несекретные поля присутствуют
        assert config_dict['flask_env'] == 'development'
        assert config_dict['use_database'] is False
    
    def test_config_boolean_parsing(self, monkeypatch):
        """Булевы значения парсятся корректно из разных форматов."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'secret')
        
        # Тестируем разные варианты true
        for true_val in ['true', 'True', 'TRUE', '1', 'yes', 'YES']:
            monkeypatch.setenv('USE_DATABASE', true_val)
            config = ConfigService()
            assert config.use_database is True, f"Failed for {true_val}"
        
        # Тестируем false
        for false_val in ['false', 'False', 'FALSE', '0', 'no', 'NO', '']:
            monkeypatch.setenv('USE_DATABASE', false_val)
            config = ConfigService()
            assert config.use_database is False, f"Failed for {false_val}"
    
    def test_config_jwt_expiration(self, monkeypatch):
        """JWT expiration корректно парсится."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'secret')
        monkeypatch.setenv('JWT_EXPIRATION_HOURS', '48')
        
        config = ConfigService()
        assert config.jwt_expiration_hours == 48
    
    def test_config_cors_origins_parsing(self, monkeypatch):
        """CORS origins корректно парсятся из строки через запятую."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'key')
        monkeypatch.setenv('JWT_SECRET_KEY', 'secret')
        monkeypatch.setenv('CORS_ORIGINS', 'http://localhost:3000, https://app.com, https://api.com')
        
        config = ConfigService()
        origins = config.cors_origins
        
        assert len(origins) == 3
        assert 'http://localhost:3000' in origins
        assert 'https://app.com' in origins
        assert 'https://api.com' in origins


def test_get_config_singleton(monkeypatch):
    """get_config() возвращает один и тот же экземпляр (singleton)."""
    monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
    monkeypatch.setenv('FERNET_ENCRYPTION_KEY', 'key')
    monkeypatch.setenv('JWT_SECRET_KEY', 'secret')
    
    from webapp.config import get_config
    
    config1 = get_config()
    config2 = get_config()
    
    assert config1 is config2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
