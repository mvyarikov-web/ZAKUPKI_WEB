"""
Главная точка входа приложения.

Это обёртка для обратной совместимости со старым кодом.
Использует новую модульную структуру из пакета webapp/.

Для разработки:
    python app.py
    
Для продакшена используйте wsgi.py:
    gunicorn 'wsgi:app' -w 2 -b 127.0.0.1:8081
"""
import os
import sys

# Убеждаемся, что рабочая директория добавлена в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем фабрику приложения
from webapp import create_app

# Создаём приложение с конфигурацией для разработки
app = create_app('dev')

if __name__ == '__main__':
    # Параметры для dev-сервера
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 8081))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 'yes')

    app.logger.info(f'Запуск dev-сервера на http://{host}:{port}')
    app.logger.info(f'Debug mode: {debug}')
    print(f'\n{"="*60}')
    print(f'🚀 Сервер запускается...')
    print(f'📍 Адрес: http://{host}:{port}')
    print(f'🔧 Debug mode: {debug}')
    print(f'{"="*60}\n')
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
