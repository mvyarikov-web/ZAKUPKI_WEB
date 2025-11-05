"""
Сервис конфигурации приложения.
Загружает настройки из переменных окружения (.env файл) с валидацией и дефолтными значениями.
"""

import os
import sys
from typing import Any, Optional
from dotenv import load_dotenv


class ConfigService:
    """
    Централизованный сервис для работы с конфигурацией приложения.
    
    Приоритет загрузки:
    1. Переменные окружения (ENV)
    2. Файл .env в корне проекта
    3. Дефолтные значения
    
    Fail-fast: критичные переменные без значений вызывают RuntimeError при инициализации.
    """
    
    # Критичные переменные (обязательны для работы приложения)
    REQUIRED_VARS = [
        'DATABASE_URL',
        'FERNET_ENCRYPTION_KEY',
        'JWT_SECRET_KEY',
    ]
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Инициализация сервиса конфигурации.
        
        Args:
            env_file: Путь к .env файлу (по умолчанию ищется в корне проекта)
        """
        # Загружаем .env файл
        if env_file:
            load_dotenv(env_file, override=False)
        else:
            # Автопоиск .env в корне проекта
            load_dotenv(override=False)
        
        # Валидация критичных переменных
        self._validate_required_vars()
    
    def _validate_required_vars(self):
        """Проверка наличия обязательных переменных окружения."""
        missing = []
        for var in self.REQUIRED_VARS:
            value = os.getenv(var)
            if not value or value.strip() == '':
                missing.append(var)
        
        if missing:
            error_msg = (
                f"КРИТИЧЕСКАЯ ОШИБКА: Отсутствуют обязательные переменные окружения:\n"
                f"{', '.join(missing)}\n\n"
                f"Действия:\n"
                f"1. Скопируйте .env.sample в .env: cp .env.sample .env\n"
                f"2. Заполните значения в .env файле\n"
                f"3. Перезапустите приложение\n\n"
                f"Подробнее: см. README.md раздел 'Настройка окружения'"
            )
            raise RuntimeError(error_msg)
    
    # ------------------------------------------------------------------------------
    # База данных
    # ------------------------------------------------------------------------------
    
    @property
    def database_url(self) -> str:
        """URL подключения к PostgreSQL."""
        return os.getenv('DATABASE_URL', '')
    
    @property
    def sql_echo(self) -> bool:
        """Логировать SQL-запросы (только для разработки)."""
        return os.getenv('SQL_ECHO', 'false').lower() == 'true'
    
    # ------------------------------------------------------------------------------
    # Шифрование и безопасность
    # ------------------------------------------------------------------------------
    
    @property
    def fernet_key(self) -> bytes:
        """Ключ шифрования Fernet для API-ключей."""
        key_str = os.getenv('FERNET_ENCRYPTION_KEY', '')
        return key_str.encode('utf-8')
    
    @property
    def jwt_secret(self) -> str:
        """Секретный ключ для подписи JWT токенов."""
        return os.getenv('JWT_SECRET_KEY', '')
    
    @property
    def jwt_algorithm(self) -> str:
        """Алгоритм подписи JWT (по умолчанию HS256)."""
        return os.getenv('JWT_ALGORITHM', 'HS256')
    
    @property
    def jwt_expiration_hours(self) -> int:
        """Время жизни JWT токена в часах."""
        return int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    
    # ------------------------------------------------------------------------------
    # Flask настройки
    # ------------------------------------------------------------------------------
    
    @property
    def flask_env(self) -> str:
        """Режим работы Flask: development, production, testing."""
        return os.getenv('FLASK_ENV', 'development')
    
    @property
    def flask_secret_key(self) -> str:
        """Секретный ключ Flask для сессий."""
        # Если не задан, используем JWT_SECRET_KEY как fallback
        return os.getenv('FLASK_SECRET_KEY', self.jwt_secret)
    
    @property
    def flask_port(self) -> int:
        """Порт для запуска Flask сервера."""
        return int(os.getenv('FLASK_PORT', '5000'))
    
    @property
    def flask_host(self) -> str:
        """Хост для прослушивания Flask сервера."""
        return os.getenv('FLASK_HOST', '127.0.0.1')
    
    # ------------------------------------------------------------------------------
    # Пути к директориям (для legacy file mode)
    # ------------------------------------------------------------------------------
    
    @property
    def BASE_DIR(self) -> str:
        """Корневая директория проекта."""
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    @property
    def UPLOAD_FOLDER(self) -> str:
        """Папка для загруженных файлов (legacy mode)."""
        return os.path.join(self.BASE_DIR, 'uploads')
    
    @property
    def INDEX_FOLDER(self) -> str:
        """Папка для индексов и технических файлов (legacy mode)."""
        return os.path.join(self.BASE_DIR, 'index')
    
    @property
    def LOGS_DIR(self) -> str:
        """Папка для логов."""
        return os.path.join(self.BASE_DIR, 'logs')
    
    @property
    def PROMPTS_FOLDER(self) -> str:
        """Папка для сохранённых промптов."""
        return os.path.join(self.BASE_DIR, 'PROMPT')
    
    @property
    def SEARCH_RESULTS_FILE(self) -> str:
        """Файл с результатами поиска (legacy mode)."""
        return os.path.join(self.INDEX_FOLDER, 'search_results.json')
    
    @property
    def SECRET_KEY(self) -> str:
        """Flask SECRET_KEY (для совместимости)."""
        return self.flask_secret_key
    
    @property
    def JSON_AS_ASCII(self) -> bool:
        """Отключить ASCII-кодирование JSON (для кириллицы)."""
        return False
    
    @property
    def MAX_CONTENT_LENGTH(self) -> int:
        """Максимальный размер загружаемого файла в байтах."""
        max_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', '100'))
        return max_mb * 1024 * 1024
    
    @property
    def REQUEST_TIMEOUT(self) -> int:
        """Таймаут обработки запроса в секундах."""
        return int(os.getenv('REQUEST_TIMEOUT', '30'))
    
    @property
    def LOG_FILE(self) -> str:
        """Путь к основному лог-файлу."""
        return os.path.join(self.LOGS_DIR, 'app.log')
    
    @property
    def LOG_LEVEL(self) -> str:
        """Уровень логирования (для совместимости)."""
        return self.log_level
    
    @property
    def LOG_BACKUP_COUNT(self) -> int:
        """Количество архивных лог-файлов."""
        return 7
    
    @property
    def JWT_SECRET_KEY(self) -> str:
        """JWT секретный ключ (Flask-совместимый)."""
        return self.jwt_secret
    
    @property
    def JWT_ALGORITHM(self) -> str:
        """JWT алгоритм (Flask-совместимый)."""
        return self.jwt_algorithm
    
    @property
    def JWT_EXPIRATION_HOURS(self) -> int:
        """JWT время жизни в часах (Flask-совместимый)."""
        return self.jwt_expiration_hours
    
    @property
    def debug_mode(self) -> bool:
        """Режим отладки (детальные трейсбэки)."""
        return os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    
    # ------------------------------------------------------------------------------
    # Dual-mode (временно, для миграции)
    # ------------------------------------------------------------------------------
    
    @property
    def use_database(self) -> bool:
        """
        Использовать БД для хранения данных.
        false = legacy режим с файлами
        true = полностью БД
        """
        value = os.getenv('USE_DATABASE', 'false').lower()
        return value in ('true', '1', 'yes', 'on')
    
    # ------------------------------------------------------------------------------
    # Логирование
    # ------------------------------------------------------------------------------
    
    @property
    def log_level(self) -> str:
        """Уровень логирования: DEBUG, INFO, WARNING, ERROR, CRITICAL."""
        return os.getenv('LOG_LEVEL', 'INFO').upper()
    
    @property
    def log_to_database(self) -> bool:
        """Логировать в БД (автоматически true при use_database=true)."""
        default = 'true' if self.use_database else 'false'
        return os.getenv('LOG_TO_DATABASE', default).lower() == 'true'
    
    @property
    def log_to_console(self) -> bool:
        """Логировать в консоль (автоматически true в development)."""
        default = 'true' if self.flask_env == 'development' else 'false'
        return os.getenv('LOG_TO_CONSOLE', default).lower() == 'true'
    
    # ------------------------------------------------------------------------------
    # Лимиты и ограничения
    # ------------------------------------------------------------------------------
    
    @property
    def max_upload_size_mb(self) -> int:
        """Максимальный размер загружаемого файла в МБ."""
        return int(os.getenv('MAX_UPLOAD_SIZE_MB', '100'))
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Максимальный размер загружаемого файла в байтах."""
        return self.max_upload_size_mb * 1024 * 1024
    
    @property
    def max_files_per_upload(self) -> int:
        """Максимальное количество файлов в одной загрузке."""
        return int(os.getenv('MAX_FILES_PER_UPLOAD', '50'))
    
    @property
    def indexing_timeout_seconds(self) -> int:
        """Таймаут для RAG-индексации в секундах."""
        return int(os.getenv('INDEXING_TIMEOUT_SECONDS', '300'))
    
    # ------------------------------------------------------------------------------
    # Форматы файлов
    # ------------------------------------------------------------------------------
    
    @property
    def ALLOWED_EXTENSIONS(self) -> set:
        """Разрешённые расширения файлов для загрузки и индексации."""
        return {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'html', 'htm', 'csv', 'tsv', 'xml', 'json'}
    
    @property
    def PREVIEW_INLINE_EXTENSIONS(self) -> set:
        """Расширения файлов, которые можно показывать inline в браузере."""
        return {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    
    @property
    def WEB_VIEWABLE_EXTENSIONS(self) -> set:
        """Расширения файлов, которые можно просматривать в веб-интерфейсе."""
        return {'html', 'htm', 'txt', 'csv', 'tsv', 'xml', 'json', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    
    # ------------------------------------------------------------------------------
    # pgvector настройки
    # ------------------------------------------------------------------------------
    
    @property
    def vector_dimension(self) -> int:
        """Размерность векторов для embeddings (1536 для OpenAI ada-002)."""
        return int(os.getenv('VECTOR_DIMENSION', '1536'))
    
    @property
    def pgvector_lists(self) -> int:
        """Количество списков для IVFFlat индекса."""
        return int(os.getenv('PGVECTOR_LISTS', '100'))
    
    # ------------------------------------------------------------------------------
    # Внешние инструменты
    # ------------------------------------------------------------------------------
    
    @property
    def tesseract_cmd(self) -> Optional[str]:
        """Путь к Tesseract OCR (если не в PATH)."""
        return os.getenv('TESSERACT_CMD')
    
    @property
    def poppler_path(self) -> Optional[str]:
        """Путь к Poppler утилитам для pdf2image."""
        return os.getenv('POPPLER_PATH')
    
    @property
    def unrar_path(self) -> Optional[str]:
        """Путь к UnRAR утилите."""
        return os.getenv('UNRAR_PATH')
    
    # ------------------------------------------------------------------------------
    # Политики ретенции
    # ------------------------------------------------------------------------------
    
    @property
    def log_retention_days(self) -> int:
        """Автоудаление логов старше N дней (0 = отключено)."""
        return int(os.getenv('LOG_RETENTION_DAYS', '90'))
    
    @property
    def search_history_retention_days(self) -> int:
        """Количество дней хранения истории поиска."""
        return int(os.getenv('SEARCH_HISTORY_RETENTION_DAYS', '30'))
    
    # ------------------------------------------------------------------------------
    # Индексация в БД (спецификация 015)
    # ------------------------------------------------------------------------------
    
    @property
    def use_db_index(self) -> bool:
        """Использовать БД для индексации вместо файлового _search_index.txt."""
        return os.getenv('USE_DB_INDEX', 'true').lower() == 'true'
    
    @property
    def chunk_size_tokens(self) -> int:
        """Размер чанка в токенах для индексации."""
        return int(os.getenv('CHUNK_SIZE_TOKENS', '500'))
    
    @property
    def chunk_overlap_tokens(self) -> int:
        """Перекрытие между чанками в токенах."""
        return int(os.getenv('CHUNK_OVERLAP_TOKENS', '50'))
    
    @property
    def auto_index_on_upload(self) -> bool:
        """Автоматически индексировать файлы при загрузке."""
        return os.getenv('AUTO_INDEX_ON_UPLOAD', 'false').lower() == 'true'
    
    @property
    def user_quota_bytes(self) -> int:
        """Квота на одного пользователя в байтах (default: 10 GB)."""
        quota_gb = float(os.getenv('USER_QUOTA_GB', '10'))
        return int(quota_gb * 1024 * 1024 * 1024)
    
    @property
    def db_storage_limit_bytes(self) -> int:
        """Глобальная квота БД в байтах (default: 100 GB)."""
        limit_gb = float(os.getenv('DB_STORAGE_LIMIT_GB', '100'))
        return int(limit_gb * 1024 * 1024 * 1024)
    
    @property
    def uploads_disabled(self) -> bool:
        """Флаг экстренной блокировки загрузок."""
        return os.getenv('UPLOADS_DISABLED', 'false').lower() == 'true'
    
    @property
    def storage_audit_log(self) -> str:
        """Путь к лог-файлу аудита хранилища."""
        return os.path.join(self.LOGS_DIR, 'storage_audit.log')
    
    # ------------------------------------------------------------------------------
    # Внутренние хелперы
    # ------------------------------------------------------------------------------
    
    @property
    def session_retention_days(self) -> int:
        """Автоудаление истёкших сессий старше N дней (0 = отключено)."""
        return int(os.getenv('SESSION_RETENTION_DAYS', '30'))
    
    # ------------------------------------------------------------------------------
    # Безопасность
    # ------------------------------------------------------------------------------
    
    @property
    def secure_cookies(self) -> bool:
        """HTTPS-only куки (true в продакшене)."""
        return os.getenv('SECURE_COOKIES', 'false').lower() == 'true'
    
    @property
    def csrf_enabled(self) -> bool:
        """CSRF-защита включена."""
        return os.getenv('CSRF_ENABLED', 'true').lower() == 'true'
    
    @property
    def cors_origins(self) -> list[str]:
        """Разрешённые origins для CORS."""
        origins_str = os.getenv('CORS_ORIGINS', '')
        if not origins_str:
            return []
        return [origin.strip() for origin in origins_str.split(',')]
    
    # ------------------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------------------
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Универсальный геттер для любых переменных окружения.
        
        Args:
            key: Имя переменной
            default: Значение по умолчанию
            
        Returns:
            Значение переменной или default
        """
        return os.getenv(key, default)
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Получить булево значение из ENV."""
        value = os.getenv(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'on')
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Получить целочисленное значение из ENV."""
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default
    
    def to_dict(self) -> dict:
        """
        Экспорт всех настроек в словарь (для отладки).
        ВНИМАНИЕ: Секретные ключи маскируются!
        """
        return {
            'database_url': self._mask_secret(self.database_url),
            'flask_env': self.flask_env,
            'flask_port': self.flask_port,
            'flask_host': self.flask_host,
            'use_database': self.use_database,
            'log_level': self.log_level,
            'log_to_database': self.log_to_database,
            'log_to_console': self.log_to_console,
            'max_upload_size_mb': self.max_upload_size_mb,
            'jwt_algorithm': self.jwt_algorithm,
            'jwt_expiration_hours': self.jwt_expiration_hours,
            'vector_dimension': self.vector_dimension,
            'secure_cookies': self.secure_cookies,
            'csrf_enabled': self.csrf_enabled,
        }
    
    @staticmethod
    def _mask_secret(value: str, visible_chars: int = 4) -> str:
        """Маскирование секретных значений для логов."""
        if not value or len(value) <= visible_chars:
            return '***'
        return f"{value[:visible_chars]}...{value[-visible_chars:]}"


# Глобальный экземпляр конфигурации (ленивая инициализация)
_config: Optional[ConfigService] = None


def get_config() -> ConfigService:
    """
    Получить глобальный экземпляр конфигурации.
    
    При первом вызове инициализирует ConfigService и валидирует критичные переменные.
    Повторные вызовы возвращают закэшированный экземпляр.
    
    Returns:
        ConfigService: Глобальный конфиг
        
    Raises:
        RuntimeError: Если отсутствуют критичные переменные окружения
    """
    global _config
    if _config is None:
        _config = ConfigService()
    return _config


# Экспорт для удобного импорта
__all__ = ['ConfigService', 'get_config']
