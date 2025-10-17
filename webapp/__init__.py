"""Flask приложение с factory pattern."""
from flask import Flask
from webapp.config import get_config
from webapp.utils.logging import setup_logging
from webapp.utils.errors import register_error_handlers
from webapp.utils.timeout_middleware import TimeoutMiddleware


def create_app(config_name=None):
    """Фабрика для создания Flask приложения.
    
    Args:
        config_name: Имя конфигурации (dev, prod, testing)
        
    Returns:
        Настроенное Flask приложение
    """
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Загружаем конфигурацию
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    
    # Создаем необходимые директории
    import os
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['INDEX_FOLDER'], exist_ok=True)
    os.makedirs(app.config['LOGS_DIR'], exist_ok=True)

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
    from webapp.routes.analysis import analysis_bp
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(analysis_bp)
    
    # Настраиваем хуки для логирования запросов
    from webapp.utils.logging import generate_request_id
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
            app.logger.info(
                '%s %s %s %.3fs %d',
                rid_str, request.method, request.path, elapsed, response.status_code
            )
        return response
    
    app.logger.info('Приложение запущено')
    
    return app
