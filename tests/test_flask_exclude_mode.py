"""Тесты для Flask API с режимом исключения (exclude_mode)."""
import pytest


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


@pytest.fixture
def test_uploads(tmp_path, flask_app):
    """Создаёт тестовую папку uploads с файлами."""
    uploads_dir = tmp_path / 'uploads'
    index_dir = tmp_path / 'index'
    uploads_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаём тестовые файлы
    (uploads_dir / "doc1.txt").write_text("Договор о поставке товаров", encoding="utf-8")
    (uploads_dir / "doc2.txt").write_text("Контракт на услуги", encoding="utf-8")
    (uploads_dir / "doc3.txt").write_text("Обычный документ без ключевых слов", encoding="utf-8")
    
    # Настраиваем приложение
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    old_index = flask_app.config.get('INDEX_FOLDER')
    
    flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)
    flask_app.config['INDEX_FOLDER'] = str(index_dir)
    
    # Создаём индекс
    from document_processor import DocumentProcessor
    dp = DocumentProcessor()
    dp.create_search_index(str(uploads_dir))
    
    # Перемещаем индекс в index папку
    import shutil
    tmp_index = uploads_dir / '_search_index.txt'
    index_path = index_dir / '_search_index.txt'
    if tmp_index.exists():
        shutil.move(str(tmp_index), str(index_path))
    
    yield flask_app, uploads_dir, index_dir
    
    # Восстанавливаем конфигурацию
    flask_app.config['UPLOAD_FOLDER'] = old_upload
    flask_app.config['INDEX_FOLDER'] = old_index


def test_search_with_exclude_mode_true(test_uploads):
    """Тест поиска с exclude_mode=True через API."""
    flask_app, uploads_dir, index_dir = test_uploads
    
    with flask_app.test_client() as client:
        # Ищем файлы, которые НЕ содержат слово "договор"
        response = client.post(
            '/search',
            json={'search_terms': 'договор', 'exclude_mode': True},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'results' in data
        
        results = data['results']
        # doc1.txt содержит "договор" - не должен быть в результатах
        # doc2.txt и doc3.txt НЕ содержат "договор" - должны быть в результатах
        filenames = [r['filename'] for r in results]
        
        assert 'doc1.txt' not in filenames
        assert 'doc2.txt' in filenames or 'doc3.txt' in filenames


def test_search_with_exclude_mode_false(test_uploads):
    """Тест обычного поиска (exclude_mode=False) через API."""
    flask_app, uploads_dir, index_dir = test_uploads
    
    with flask_app.test_client() as client:
        # Обычный поиск: ищем файлы, которые СОДЕРЖАТ слово "договор"
        response = client.post(
            '/search',
            json={'search_terms': 'договор', 'exclude_mode': False},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'results' in data
        
        results = data['results']
        # doc1.txt содержит "договор" - должен быть в результатах
        filenames = [r['filename'] for r in results]
        assert 'doc1.txt' in filenames


def test_search_without_exclude_mode_parameter(test_uploads):
    """Тест что без параметра exclude_mode работает обычный поиск."""
    flask_app, uploads_dir, index_dir = test_uploads
    
    with flask_app.test_client() as client:
        # Не передаём exclude_mode - должен быть обычный поиск
        response = client.post(
            '/search',
            json={'search_terms': 'договор'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'results' in data
        
        results = data['results']
        # doc1.txt содержит "договор" - должен быть в результатах
        filenames = [r['filename'] for r in results]
        assert 'doc1.txt' in filenames


def test_search_exclude_mode_with_prefix(test_uploads):
    """Тест что в exclude_mode результаты содержат префикс 'не содержит'."""
    flask_app, uploads_dir, index_dir = test_uploads
    
    with flask_app.test_client() as client:
        response = client.post(
            '/search',
            json={'search_terms': 'договор', 'exclude_mode': True},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        results = data['results']
        
        # Проверяем, что в результатах есть файлы без слова "договор"
        if results:
            # Проверяем структуру результата
            for result in results:
                if 'per_term' in result:
                    for term_entry in result['per_term']:
                        term = term_entry.get('term', '')
                        # В exclude_mode термины должны начинаться с "не содержит:"
                        if term:
                            assert term.startswith('не содержит:')
