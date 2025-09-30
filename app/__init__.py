"""Flask приложение с factory pattern."""
from flask import Flask
from app.config import get_config
from app.utils.logging import setup_logging
from app.utils.errors import register_error_handlers


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
    
    # Настраиваем логирование
    setup_logging(app)
    
    # Регистрируем обработчики ошибок
    register_error_handlers(app)
    
    # Регистрируем blueprints
    from app.routes.pages import pages_bp
    from app.routes.files import files_bp
    from app.routes.search import search_bp
    from app.routes.health import health_bp
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(health_bp)
    
    # Настраиваем хуки для логирования запросов
    from app.utils.logging import generate_request_id
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
