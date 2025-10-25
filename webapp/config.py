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
    PROMPTS_FOLDER = os.path.join(BASE_DIR, 'PROMPT')
    
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
    
    # Расширения файлов (архивы исключены)
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'html', 'htm', 'csv', 'tsv', 'xml', 'json'}
    PREVIEW_INLINE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    WEB_VIEWABLE_EXTENSIONS = {'html', 'htm', 'txt', 'csv', 'tsv', 'xml', 'json', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    
    # PDF Processing
    PDF_TEXT_TIMEOUT_S = 5  # тайм-бюджет для извлечения текста из векторных PDF
    PDF_OCR_ENABLED = True  # включить OCR для сканов
    PDF_OCR_MAX_PAGES = 2   # максимум страниц для OCR (оптимизация)
    PDF_OCR_LANG = 'rus+eng'  # языки для Tesseract
    PDF_TEXT_MIN_LEN = 50   # порог минимальной длины текста (ниже — считать сканом)
    PDF_MAX_PAGES_TEXT = 100  # лимит страниц для векторного извлечения
    
    # OCR Configuration (increment-013)
    OCR_TIMEOUT_PER_PAGE = 30  # таймаут на страницу OCR (секунды)
    OCR_PREPROCESS_ENABLED = False  # предобработка изображений перед OCR
    OCR_USE_OSD = False  # определение ориентации страниц (OSD)
    OCR_PARALLEL_PAGES = False  # параллельная обработка страниц
    OCR_MAX_WORKERS = 4  # максимум потоков для параллельного OCR
    
    # OpenAI GPT API Configuration
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')  # API ключ для GPT
    GPT_MODEL = 'gpt-3.5-turbo'  # Модель GPT
    GPT_MAX_TOKENS = 150  # Максимум токенов в ответе
    GPT_TEMPERATURE = 0.7  # Температура генерации (0-1)
    GPT_MAX_REQUEST_SIZE = 4096  # Максимальный размер запроса (символы)
    
    # RAG Configuration
    RAG_ENABLED = os.environ.get('RAG_ENABLED', 'true').lower() in ('true', '1', 'yes')
    RAG_CHUNK_SIZE = int(os.environ.get('RAG_CHUNK_SIZE', '2000'))  # Токены на чанк
    RAG_CHUNK_OVERLAP = int(os.environ.get('RAG_CHUNK_OVERLAP', '3'))  # Предложений overlap
    RAG_TOP_K = int(os.environ.get('RAG_TOP_K', '5'))  # Количество чанков для контекста
    RAG_MIN_SIMILARITY = float(os.environ.get('RAG_MIN_SIMILARITY', '0.7'))  # Порог релевантности
    RAG_EMBEDDING_MODEL = os.environ.get('RAG_EMBEDDING_MODEL', 'text-embedding-3-small')
    RAG_DEFAULT_MODEL = os.environ.get('RAG_DEFAULT_MODEL', 'gpt-4o-mini')
    RAG_MAX_OUTPUT_TOKENS = int(os.environ.get('RAG_MAX_OUTPUT_TOKENS', '600'))
    RAG_TEMPERATURE = float(os.environ.get('RAG_TEMPERATURE', '0.3'))  # Более детерминированный
    RAG_MODELS_FILE = os.path.join(BASE_DIR, 'index', 'models.json')
    RAG_HYBRID_SEARCH = True  # Семантика + ключевые слова
    
    # PostgreSQL Configuration (для векторного поиска)
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', '5432'))
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'zakupki_rag')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')
    DATABASE_URL = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'
    )


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
