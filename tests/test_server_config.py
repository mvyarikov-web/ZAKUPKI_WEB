"""Тесты для проверки конфигурации сервера."""
import os


def test_server_default_config():
    """Проверяет, что app.py использует правильные значения по умолчанию."""
    # Импортируем модуль app (но не запускаем сервер)
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Сохраняем оригинальные переменные окружения
    original_host = os.environ.get('FLASK_HOST')
    original_port = os.environ.get('FLASK_PORT')
    original_debug = os.environ.get('FLASK_DEBUG')
    
    try:
        # Удаляем переменные окружения для теста дефолтных значений
        for key in ['FLASK_HOST', 'FLASK_PORT', 'FLASK_DEBUG']:
            if key in os.environ:
                del os.environ[key]
        
        # Проверяем дефолтные значения
        expected_host = '127.0.0.1'
        expected_port = 8081
        expected_debug = True
        
        # Читаем код app.py и проверяем дефолты
        with open('app.py', 'r', encoding='utf-8') as f:
            app_code = f.read()
        
        # Проверяем, что дефолтные значения правильные
        assert "FLASK_HOST', '127.0.0.1'" in app_code, \
            "app.py должен использовать '127.0.0.1' как дефолтный хост"
        assert "FLASK_PORT', 8081)" in app_code, \
            "app.py должен использовать 8081 как дефолтный порт"
        
    finally:
        # Восстанавливаем переменные окружения
        if original_host is not None:
            os.environ['FLASK_HOST'] = original_host
        if original_port is not None:
            os.environ['FLASK_PORT'] = original_port
        if original_debug is not None:
            os.environ['FLASK_DEBUG'] = original_debug


def test_server_env_variable_usage():
    """Проверяет, что app.py читает переменные окружения."""
    # Читаем код app.py
    with open('app.py', 'r', encoding='utf-8') as f:
        app_code = f.read()
    
    # Проверяем, что используются переменные окружения
    assert "os.environ.get('FLASK_HOST'" in app_code, \
        "app.py должен читать FLASK_HOST из переменных окружения"
    assert "os.environ.get('FLASK_PORT'" in app_code, \
        "app.py должен читать FLASK_PORT из переменных окружения"
    assert "os.environ.get('FLASK_DEBUG'" in app_code, \
        "app.py должен читать FLASK_DEBUG из переменных окружения"
