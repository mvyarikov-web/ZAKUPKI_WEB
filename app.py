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
import signal
from werkzeug.serving import make_server

# Убеждаемся, что рабочая директория добавлена в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем фабрику приложения
from webapp import create_app

# Создаём приложение с конфигурацией для разработки
app = create_app('dev')

# Глобальная переменная для сервера
server = None


def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения."""
    print('\n🛑 Получен сигнал завершения. Останавливаем сервер...')
    if server:
        try:
            server.shutdown()
        except Exception:
            pass
    sys.exit(0)


if __name__ == '__main__':
    # Параметры для dev-сервера
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 8081))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

    # Регистрируем обработчики сигналов
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception:
        # Не во всех окружениях доступна регистрация сигналов (например, Windows или IDE)
        pass

    app.logger.info(f'Запуск dev-сервера на http://{host}:{port}')
    app.logger.info(f'Debug mode: {debug}')
    print(f'\n{"="*60}')
    print('🚀 Сервер запускается...')
    print(f'📍 Адрес: http://{host}:{port}')
    print(f'🔧 Debug mode: {debug}')
    print('⏱️ Таймаут запросов (WSGI): 120 секунд')
    print(f'{"="*60}\n')

    try:
        # Используем werkzeug сервер с таймаутом
        server = make_server(host, port, app, threaded=True)
        try:
            server.timeout = 120  # секунды (увеличено для долгих AI-анализов)
        except Exception:
            pass

        print(f'✅ Сервер запущен и слушает на {host}:{port}')
        print('Нажмите Ctrl+C для остановки')

        server.serve_forever()

    except KeyboardInterrupt:
        print('\n🛑 Сервер остановлен пользователем')
    except Exception as e:
        print(f'❌ Ошибка запуска сервера: {e}')
        sys.exit(1)
    finally:
        if server:
            try:
                server.shutdown()
            except Exception:
                pass
        print('👋 Сервер завершён')
