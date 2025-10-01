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
    import socket

    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    # Предпочитаемый порт можно задать через FLASK_PORT (по умолчанию 8081)
    preferred_port = int(os.environ.get('FLASK_PORT', 8081))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 'yes')
    use_reloader = os.environ.get('FLASK_RELOAD', 'False').lower() in ('true', '1', 'yes')

    def _is_port_free(h: str, p: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((h, p))
            return True
        except OSError:
            return False

    # Подбор свободного порта: 8081 → 5000 → 8080 → выбрать эфемерный (0)
    candidates_base = (8081, 5000, 8080)
    candidates = [preferred_port] + [p for p in candidates_base if p != preferred_port]
    chosen_port = None
    for p in candidates:
        if _is_port_free(host, p):
            chosen_port = p
            break
    if chosen_port is None:
        # пусть ОС выделит свободный порт
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            chosen_port = s.getsockname()[1]
    port = chosen_port
    
    app.logger.info(f'Запуск dev-сервера на http://{host}:{port}')
    app.logger.info(f'Debug mode: {debug}; Reloader: {use_reloader}')
    
    # Запуск встроенного Flask-сервера (только для разработки!)
    # Отключаем reloader по умолчанию, чтобы избежать двойного запуска и коллизий портов на macOS
    app.run(host=host, port=port, debug=debug, use_reloader=use_reloader, threaded=True)
