"""Настройка логирования приложения."""
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import uuid


def setup_logging(app):
    """Настраивает логирование для приложения.
    
    Использует двойную стратегию:
    1. Файловое логирование (для отладки и резервного копирования)
    2. Логирование в PostgreSQL (для аналитики и мониторинга)
    
    Args:
        app: Flask приложение
    """
    logs_dir = app.config.get('LOGS_DIR')
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = app.config.get('LOG_FILE')
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
    backup_count = app.config.get('LOG_BACKUP_COUNT', 7)
    
    # === 1. Файловый handler (legacy, для совместимости) ===
    file_handler = TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=backup_count, encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(module)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # === 2. Database handler (новый, основной) ===
    try:
        from webapp.utils.db_log_handler import DatabaseLogHandler
        db_handler = DatabaseLogHandler(level=log_level)
        db_handler.setFormatter(formatter)
        use_db_logging = True
    except Exception as e:
        db_handler = None
        use_db_logging = False
        print(f'⚠️ Не удалось инициализировать БД логирование: {e}')
    
    # Настраиваем логгер приложения
    app.logger.handlers = []
    app.logger.addHandler(file_handler)
    if use_db_logging and db_handler:
        app.logger.addHandler(db_handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False
    
    # Приглушаем werkzeug
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Настраиваем корневой логгер для всех модулей
    root_logger = logging.getLogger()
    if file_handler not in root_logger.handlers:
        root_logger.addHandler(file_handler)
    if use_db_logging and db_handler and db_handler not in root_logger.handlers:
        root_logger.addHandler(db_handler)
    if root_logger.level > log_level:
        root_logger.setLevel(log_level)
    
    log_targets = f'{log_file}'
    if use_db_logging:
        log_targets += ' + PostgreSQL (app_logs)'
    app.logger.info('Логирование настроено: %s', log_targets)


def generate_request_id():
    """Генерирует уникальный ID для запроса.
    
    Returns:
        str: Hex-представление UUID
    """
    try:
        return uuid.uuid4().hex
    except Exception:
        return None
