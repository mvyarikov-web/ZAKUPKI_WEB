"""Обработчики ошибок приложения."""
from flask import jsonify, request, render_template


def register_error_handlers(app):
    """Регистрирует обработчики ошибок для приложения.
    
    Args:
        app: Flask приложение
    """
    
    @app.errorhandler(413)
    def request_entity_too_large(e):
        """Обработчик ошибки слишком большого файла."""
        app.logger.warning('413 Request Entity Too Large')
        if request.is_json or request.path.startswith('/api'):
            return jsonify({'error': 'Файл слишком большой. Лимит 100MB.'}), 413
        
        # Проверяем наличие шаблона
        if _template_exists('error.html'):
            return render_template('error.html', error='Файл слишком большой. Лимит 100MB.'), 413
        else:
            # Fallback: простой HTML без шаблона
            return '<h1>413 - Файл слишком большой</h1><p>Размер файла превышает лимит 100MB.</p>', 413
    
    @app.errorhandler(404)
    def not_found(e):
        """Обработчик ошибки 404."""
        if request.is_json or request.path.startswith('/api'):
            return jsonify({'error': 'Ресурс не найден'}), 404
        
        # Проверяем наличие шаблонов
        if _template_exists('error.html'):
            return render_template('error.html', error='Страница не найдена'), 404
        elif _template_exists('404.html'):
            return render_template('404.html', error='Страница не найдена'), 404
        else:
            # Fallback: простой HTML без шаблона
            return '<h1>404 - Страница не найдена</h1><p>Запрошенная страница не существует.</p>', 404
    
    @app.errorhandler(500)
    def internal_error(e):
        """Обработчик внутренней ошибки сервера."""
        app.logger.exception('Internal server error')
        
        # Логируем ошибку в БД
        try:
            from webapp.utils.db_log_handler import ErrorLogHandler
            ErrorLogHandler.log_error(app, e, component='error_handler')
        except Exception as log_err:
            app.logger.debug(f'Не удалось записать ошибку в БД: {log_err}')
        
        if request.is_json or request.path.startswith('/api'):
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
        
        # Проверяем наличие шаблонов
        if _template_exists('error.html'):
            return render_template('error.html', error='Внутренняя ошибка сервера'), 500
        elif _template_exists('500.html'):
            return render_template('500.html', error='Внутренняя ошибка сервера'), 500
        else:
            # Fallback: простой HTML без шаблона
            return '<h1>500 - Внутренняя ошибка сервера</h1><p>Произошла ошибка при обработке запроса.</p>', 500


def _template_exists(template_name):
    """Проверяет существование шаблона."""
    try:
        from flask import current_app
        current_app.jinja_env.get_template(template_name)
        return True
    except Exception:
        return False
