"""Конфигурация приложения для различных окружений."""
import os


class Config:
    """Базовая конфигурация."""
    
    # Безопасность
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Пути
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    INDEX_FOLDER = os.path.join(BASE_DIR, 'index')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    
    # Flask
    JSON_AS_ASCII = False  # корректная кириллица в JSON
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
    REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', '30'))  # таймаут обработки запроса (сек)
    
    # Приложение
    SEARCH_RESULTS_FILE = os.path.join(BASE_DIR, 'index', 'search_results.json')
    
    # Логирование
    LOG_FILE = os.path.join(LOGS_DIR, 'app.log')
    LOG_LEVEL = 'INFO'
    LOG_BACKUP_COUNT = 7
    
    # Расширения файлов
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'html', 'htm', 'csv', 'tsv', 'xml', 'json', 'zip', 'rar'}
    PREVIEW_INLINE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    WEB_VIEWABLE_EXTENSIONS = {'html', 'htm', 'txt', 'csv', 'tsv', 'xml', 'json', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    
    # PDF Processing
    PDF_TEXT_TIMEOUT_S = 5  # тайм-бюджет для извлечения текста из векторных PDF
    PDF_OCR_ENABLED = True  # включить OCR для сканов
    PDF_OCR_MAX_PAGES = 2   # максимум страниц для OCR (оптимизация)
    PDF_OCR_LANG = 'rus+eng'  # языки для Tesseract
    PDF_TEXT_MIN_LEN = 50   # порог минимальной длины текста (ниже — считать сканом)
    PDF_MAX_PAGES_TEXT = 100  # лимит страниц для векторного извлечения


class DevConfig(Config):
    """Конфигурация для разработки."""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProdConfig(Config):
    """Конфигурация для продакшена."""
    DEBUG = False
    LOG_LEVEL = 'INFO'


class TestingConfig(Config):
    """Конфигурация для тестирования."""
    TESTING = True
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


# Маппинг конфигураций
config_by_name = {
    'dev': DevConfig,
    'prod': ProdConfig,
    'testing': TestingConfig,
    'default': DevConfig
}


def get_config(config_name=None):
    """Получить конфигурацию по имени или из переменной окружения."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    return config_by_name.get(config_name, DevConfig)
