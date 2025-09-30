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
        return render_template('error.html', error='Файл слишком большой. Лимит 100MB.'), 413
    
    @app.errorhandler(404)
    def not_found(e):
        """Обработчик ошибки 404."""
        if request.is_json or request.path.startswith('/api'):
            return jsonify({'error': 'Ресурс не найден'}), 404
        return render_template('error.html' if _template_exists('error.html') else '404.html', 
                             error='Страница не найдена'), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        """Обработчик внутренней ошибки сервера."""
        app.logger.exception('Internal server error')
        if request.is_json or request.path.startswith('/api'):
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
        return render_template('error.html' if _template_exists('error.html') else '500.html',
                             error='Внутренняя ошибка сервера'), 500


def _template_exists(template_name):
    """Проверяет существование шаблона."""
    try:
        from flask import current_app
        current_app.jinja_env.get_template(template_name)
        return True
    except Exception:
        return False
