"""WSGI точка входа для продакшен-развёртывания.

Использование с gunicorn:
    gunicorn 'wsgi:app' -w 2 -b 127.0.0.1:8081

Использование с uwsgi:
    uwsgi --http :8081 --wsgi-file wsgi.py --callable app
"""
import os
from webapp import create_app

# Получаем имя конфигурации из переменной окружения
config_name = os.environ.get('FLASK_ENV', 'prod')

# Создаём приложение
app = create_app(config_name)

if __name__ == '__main__':
    # Для разработки можно запускать напрямую
    # Для продакшена используйте gunicorn (см. документацию выше)
    app.run(host='127.0.0.1', port=8081)
