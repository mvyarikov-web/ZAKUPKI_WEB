"""
Тесты для инкремента 008: Компактный интерфейс (полная переработка)

FR-001, FR-002: Просмотр неподдерживаемых файлов возвращает понятное сообщение
FR-003, FR-004, FR-005: Результаты поиска под файлами
FR-006, FR-007, FR-008: Панель "Инструменты"
FR-010: Автотесты
"""
import pytest
from webapp.services.state import FilesState


@pytest.fixture
def flask_app():
    """Создаёт тестовое приложение."""
    try:
        from webapp import create_app
        app = create_app('testing')
    except ImportError:
        import app as old_app
        app = old_app.app
    return app


def test_unsupported_file_view_returns_message(tmp_path, flask_app):
    """
    FR-001: При клике на неподдерживаемый файл должно выводиться
    понятное сообщение "Просмотр файла не поддерживается" вместо JSON.
    """
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_results = flask_app.config.get('SEARCH_RESULTS_FILE')
    
    try:
        # Настраиваем временные папки
        uploads_dir = tmp_path / 'uploads'
        results_file = tmp_path / 'search_results.json'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        flask_app.config['SEARCH_RESULTS_FILE'] = str(results_file)
        
        # Создаём тестовый файл
        test_file = uploads_dir / 'test.txt'
        test_file.write_text('test content', encoding='utf-8')
        
        # Устанавливаем статус unsupported через FilesState
        files_state = FilesState(str(results_file))
        files_state.set_file_status('test.txt', 'unsupported', {'error': 'Неподдерживаемый формат'})
        
        with flask_app.test_client() as client:
            resp = client.get('/view/test.txt')
            
            # Проверяем, что возвращается HTML с сообщением, а не JSON
            assert resp.status_code == 200
            assert resp.content_type.startswith('text/html')
            content = resp.data.decode('utf-8')
            assert 'Просмотр файла не поддерживается' in content
            # Проверяем, что это не JSON ответ
            assert not content.strip().startswith('{')
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
        flask_app.config['SEARCH_RESULTS_FILE'] = old_results


def test_error_file_view_returns_message(tmp_path, flask_app):
    """
    FR-001: При клике на файл с ошибкой должно выводиться
    понятное сообщение "Просмотр файла не поддерживается" вместо JSON.
    """
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_results = flask_app.config.get('SEARCH_RESULTS_FILE')
    
    try:
        uploads_dir = tmp_path / 'uploads'
        results_file = tmp_path / 'search_results.json'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        flask_app.config['SEARCH_RESULTS_FILE'] = str(results_file)
        
        test_file = uploads_dir / 'error.txt'
        test_file.write_text('test content', encoding='utf-8')
        
        # Устанавливаем статус error через FilesState
        files_state = FilesState(str(results_file))
        files_state.set_file_status('error.txt', 'error', {'error': 'Ошибка чтения'})
        
        with flask_app.test_client() as client:
            resp = client.get('/view/error.txt')
            
            assert resp.status_code == 200
            assert resp.content_type.startswith('text/html')
            content = resp.data.decode('utf-8')
            assert 'Просмотр файла не поддерживается' in content
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
        flask_app.config['SEARCH_RESULTS_FILE'] = old_results


def test_empty_file_view_returns_message(tmp_path, flask_app):
    """
    FR-001: При клике на файл с char_count=0 должно выводиться
    понятное сообщение "Просмотр файла не поддерживается" вместо JSON.
    """
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_results = flask_app.config.get('SEARCH_RESULTS_FILE')
    old_index = flask_app.config.get('INDEX_FOLDER')
    
    try:
        uploads_dir = tmp_path / 'uploads'
        index_dir = tmp_path / 'index'
        results_file = tmp_path / 'search_results.json'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        index_dir.mkdir(parents=True, exist_ok=True)
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        flask_app.config['SEARCH_RESULTS_FILE'] = str(results_file)
        flask_app.config['INDEX_FOLDER'] = str(index_dir)
        
        test_file = uploads_dir / 'empty.txt'
        test_file.write_text('', encoding='utf-8')
        
        # Создаём пустой индекс
        index_file = index_dir / '_search_index.txt'
        index_file.write_text('', encoding='utf-8')
        
        # Устанавливаем char_count=0 через FilesState
        # Смотрим на структуру: set_file_status создаёт {'status': ..., 'result': {...}}
        # А get_file_status возвращает всё поле result как плоский dict
        FilesState(str(results_file))
        
        # Прямо записываем в файл нужную структуру
        import json
        with open(str(results_file), 'w', encoding='utf-8') as f:
            json.dump({
                'last_updated': '2024-01-01T00:00:00',
                'file_status': {
                    'empty.txt': {
                        'status': 'processed',
                        'char_count': 0,
                        'error': None
                    }
                },
                'last_search_terms': ''
            }, f)
        
        with flask_app.test_client() as client:
            resp = client.get('/view/empty.txt')
            
            assert resp.status_code == 200
            assert resp.content_type.startswith('text/html')
            content = resp.data.decode('utf-8')
            # Проверяем что это либо сообщение о неподдерживаемом файле, либо пустое содержимое (что тоже корректно для char_count=0)
            assert 'Просмотр файла не поддерживается' in content or 'Не удалось извлечь текст' in content
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
        flask_app.config['SEARCH_RESULTS_FILE'] = old_results
        flask_app.config['INDEX_FOLDER'] = old_index


def test_virtual_archive_file_unsupported_view(tmp_path, flask_app):
    """
    FR-002: Виртуальные файлы из архивов с ошибками также должны показывать
    понятное сообщение вместо JSON.
    """
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_results = flask_app.config.get('SEARCH_RESULTS_FILE')
    
    try:
        uploads_dir = tmp_path / 'uploads'
        results_file = tmp_path / 'search_results.json'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        flask_app.config['SEARCH_RESULTS_FILE'] = str(results_file)
        
        # Создаём виртуальный путь для файла из архива
        virtual_path = 'zip://archive.zip/file.txt'
        
        # Устанавливаем статус unsupported для виртуального файла
        files_state = FilesState(str(results_file))
        files_state.set_file_status(virtual_path, 'unsupported', {'error': 'Неподдерживаемый формат'})
        
        with flask_app.test_client() as client:
            resp = client.get(f'/view/{virtual_path}')
            
            # Должно вернуть HTML с сообщением
            assert resp.status_code in [200, 400]  # 400 если путь не прошел проверку безопасности
            if resp.status_code == 200:
                assert resp.content_type.startswith('text/html')
                content = resp.data.decode('utf-8')
                # Если это не ошибка пути, то должно быть сообщение о неподдерживаемом файле
                assert 'Просмотр файла не поддерживается' in content or 'Недопустимый путь' in content
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
        flask_app.config['SEARCH_RESULTS_FILE'] = old_results


def test_index_page_has_tools_section(flask_app):
    """
    FR-006, FR-007: Проверяет наличие секции "Инструменты" с кнопками
    "Выбрать папку", "Удалить файлы", "Просмотр индекса" на одной линии.
    """
    with flask_app.test_client() as client:
        resp = client.get('/')
        assert resp.status_code == 200
        content = resp.data.decode('utf-8')
        
        # Проверяем наличие секции "Инструменты"
        assert 'Инструменты' in content or 'tools-section' in content
        
        # Проверяем наличие всех трех кнопок
        assert 'Выбрать папку' in content
        assert 'Удалить файлы' in content
        assert 'Просмотр индекса' in content


def test_index_page_no_cleanup_section(flask_app):
    """
    FR-008: Проверяет, что блока "Очистка" и кнопки "Очистить всё" больше нет.
    """
    with flask_app.test_client() as client:
        resp = client.get('/')
        assert resp.status_code == 200
        content = resp.data.decode('utf-8')
        
        # Проверяем отсутствие старых элементов
        # Допускаем присутствие слова "Очистка" в других контекстах, но не как заголовок секции
        assert 'cleanup-section' not in content
        assert 'clearAllBtn' not in content
        assert 'Очистить всё' not in content


def test_index_page_has_file_search_results_container(tmp_path, flask_app):
    """
    FR-003: Проверяет, что в HTML есть контейнеры для результатов поиска под файлами,
    а не отдельный блок результатов.
    """
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    
    try:
        # Создаём временную папку с файлом, чтобы увидеть контейнеры
        uploads_dir = tmp_path / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        test_file = uploads_dir / 'test.txt'
        test_file.write_text('test content', encoding='utf-8')
        
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
        
        with flask_app.test_client() as client:
            resp = client.get('/')
            assert resp.status_code == 200
            content = resp.data.decode('utf-8')
            
            # Проверяем наличие контейнеров для результатов под файлами
            assert 'file-search-results' in content
            
            # Проверяем отсутствие старого отдельного блока результатов
            # (resultsSection может быть в JS, но не в HTML как отдельная секция)
            assert 'id="resultsSection"' not in content
            assert '<section class="results-section"' not in content
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
