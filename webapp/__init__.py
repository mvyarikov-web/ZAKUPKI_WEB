"""Flask приложение с factory pattern."""
from flask import Flask
from webapp.config import get_config
from webapp.utils.logging import setup_logging
from webapp.utils.errors import register_error_handlers
from webapp.utils.timeout_middleware import TimeoutMiddleware
import os


def _load_env_from_dotenv() -> None:
    """Загрузить переменные из .env, если файл существует.

    Без внешних зависимостей: читаем ключ=значение, игнорируем комментарии и пустые строки.
    Не переопределяем уже установленные переменные окружения.
    """
    try:
        # Корень проекта: папка выше webapp/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(base_dir, '.env')
        if not os.path.exists(env_path):
            return

        with open(env_path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[len('export '):].lstrip()
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Любые ошибки чтения .env не должны ломать запуск приложения
        pass


def create_app(config_name=None):
    """Фабрика для создания Flask приложения.
    
    Args:
        config_name: Имя конфигурации (dev, prod, testing)
        
    Returns:
        Настроенное Flask приложение
    """
    # Сначала пробуем загрузить переменные окружения из .env
    _load_env_from_dotenv()
    
    # Диагностика: проверяем загрузку OpenAI ключа (только факт наличия, не значение)
    api_key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if api_key_present:
        print("✓ OpenAI API ключ загружен из окружения")
    else:
        print("⚠️ OpenAI API ключ не найден в окружении")

    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )
    
    # Загружаем конфигурацию (singleton ConfigService)
    config_service = get_config()
    app.config.from_object(config_service)
    
    # Дополнительно устанавливаем property-атрибуты, которые from_object не копирует
    app.config['use_database'] = config_service.use_database
    app.config['ALLOWED_EXTENSIONS'] = config_service.ALLOWED_EXTENSIONS
    app.config['PREVIEW_INLINE_EXTENSIONS'] = config_service.PREVIEW_INLINE_EXTENSIONS
    app.config['WEB_VIEWABLE_EXTENSIONS'] = config_service.WEB_VIEWABLE_EXTENSIONS
    app.config['FERNET_ENCRYPTION_KEY'] = config_service.fernet_key.decode('utf-8')
    
    # Создаем необходимые директории
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['INDEX_FOLDER'], exist_ok=True)
    os.makedirs(app.config['LOGS_DIR'], exist_ok=True)
    # PROMPTS_FOLDER больше не используется - промпты хранятся в БД

    # Таймаут для долгих запросов (например, сборка индекса)
    try:
        timeout_seconds = int(app.config.get('REQUEST_TIMEOUT', 30))
    except Exception:
        timeout_seconds = 30
    app.wsgi_app = TimeoutMiddleware(
        app.wsgi_app,
        timeout=timeout_seconds,
        skip_paths=[
            '/static/',          # статика не ограничивается
            '/download/',        # скачивания
            '/ai_rag/analyze',   # AI-анализ с собственным таймаутом модели
            '/build_index',      # индексация может быть долгой
        ]
    )
    
        # Настраиваем логирование
    setup_logging(app)
    
    # Регистрируем обработчики ошибок
    register_error_handlers(app)
    
    # Регистрируем blueprints
    from webapp.routes.pages import pages_bp
    from webapp.routes.files import files_bp
    from webapp.routes.search import search_bp
    from webapp.routes.health import health_bp
    from webapp.routes.ai_analysis import ai_analysis_bp
    from webapp.routes.ai_rag import ai_rag_bp
    from webapp.routes.auth import auth_bp
    from webapp.routes.prompts import prompts_bp
    from webapp.routes.admin import admin_bp
    
    # Используем БД-версию API ключей вместо legacy
    from webapp.routes.api_keys_db import api_keys_new_bp
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(ai_analysis_bp)
    app.register_blueprint(ai_rag_bp)
    app.register_blueprint(api_keys_new_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(prompts_bp)
    app.register_blueprint(admin_bp)
    
    # Настраиваем auth middleware
    from webapp.middleware.auth_middleware import setup_auth_middleware
    setup_auth_middleware(app)
    
    # Настраиваем хуки для логирования запросов
    from webapp.utils.logging import generate_request_id
    from webapp.utils.db_log_handler import HTTPRequestLogHandler
    import time
    from flask import g
    
    @app.before_request
    def _start_timer():
        g._start_time = time.time()
        g.rid = generate_request_id()
    
    @app.after_request
    def _log_request(response):
        if hasattr(g, '_start_time'):
            elapsed = time.time() - g._start_time
            from flask import request
            rid_str = f'[{g.rid[:8]}]' if hasattr(g, 'rid') and g.rid else ''
            
            # Логируем в файл (legacy)
            app.logger.info(
                '%s %s %s %.3fs %d',
                rid_str, request.method, request.path, elapsed, response.status_code
            )
            
            # Логируем в БД (новый подход)
            # Исключаем статические файлы и health check
            if not request.path.startswith('/static/') and request.path != '/health':
                try:
                    HTTPRequestLogHandler.log_request(app, request, response, g._start_time)
                except Exception as e:
                    app.logger.debug(f'Ошибка записи HTTP лога в БД: {e}')
        
        return response
    
    app.logger.info('Приложение запущено')
    
    return app
