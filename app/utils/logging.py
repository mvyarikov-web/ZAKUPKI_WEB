"""Настройка логирования приложения."""
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import uuid


def setup_logging(app):
    """Настраивает логирование для приложения.
    
    Args:
        app: Flask приложение
    """
    logs_dir = app.config.get('LOGS_DIR')
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = app.config.get('LOG_FILE')
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
    backup_count = app.config.get('LOG_BACKUP_COUNT', 7)
    
    # Создаем обработчик с ротацией
    handler = TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=backup_count, encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(module)s:%(lineno)d - %(message)s'
    )
    handler.setFormatter(formatter)
    handler.setLevel(log_level)
    
    # Настраиваем логгер приложения
    app.logger.handlers = []
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False
    
    # Приглушаем werkzeug
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Настраиваем корневой логгер для всех модулей
    root_logger = logging.getLogger()
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)
    if root_logger.level > log_level:
        root_logger.setLevel(log_level)
    
    app.logger.info('Логирование настроено: %s', log_file)


def generate_request_id():
    """Генерирует уникальный ID для запроса.
    
    Returns:
        str: Hex-представление UUID
    """
    try:
        return uuid.uuid4().hex
    except Exception:
        return None
