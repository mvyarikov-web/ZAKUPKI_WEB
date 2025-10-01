"""
Автотест для проверки корректности светофоров и счётчиков совпадений.
Тестирует:
1. Жёлтые светофоры для обычных файлов без совпадений
2. Корректность счётчиков совпадений
3. Отсутствие дублирования результатов
"""
import os
import tempfile
import pytest
import json
from webapp import create_app
from webapp.services.state import FilesState


@pytest.fixture
def app():
    """Создаёт тестовое приложение Flask."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    app.config['INDEX_FOLDER'] = tempfile.mkdtemp() 
    app.config['SEARCH_RESULTS_FILE'] = os.path.join(app.config['INDEX_FOLDER'], 'search_results.json')
    return app


@pytest.fixture
def client(app):
    """Создаёт тестовый клиент."""
    return app.test_client()


@pytest.fixture
def test_files(app):
    """Создаёт тестовые файлы для проверки."""
    uploads_dir = app.config['UPLOAD_FOLDER']
    
    # Создаём обычную папку с файлами
    regular_folder = os.path.join(uploads_dir, 'regular_folder')
    os.makedirs(regular_folder, exist_ok=True)
    
    # Файл с совпадениями
    with open(os.path.join(regular_folder, 'file_with_matches.txt'), 'w', encoding='utf-8') as f:
        f.write('Это тестовый файл с ключевым словом монтаж. Монтаж выполняется качественно.')
    
    # Файл без совпадений  
    with open(os.path.join(regular_folder, 'file_without_matches.txt'), 'w', encoding='utf-8') as f:
        f.write('Это обычный текстовый файл без искомых слов. Здесь только обычная информация.')
    
    # Файл с другими словами
    with open(os.path.join(regular_folder, 'another_file.txt'), 'w', encoding='utf-8') as f:
        f.write('Документация по проекту. Содержит описание функций и методов.')
    
    return {
        'regular_folder': regular_folder,
        'file_with_matches': 'regular_folder/file_with_matches.txt',
        'file_without_matches': 'regular_folder/file_without_matches.txt', 
        'another_file': 'regular_folder/another_file.txt'
    }


def test_traffic_lights_and_counters(client, app, test_files):
    """Тестирует корректность светофоров и счётчиков."""
    
    with app.app_context():
        # 1. Строим индекс
        response = client.post('/build_index')
        assert response.status_code == 200
        
        # 2. Выполняем поиск по слову "монтаж"
        response = client.post('/search', 
                             json={'search_terms': 'монтаж'},
                             content_type='application/json')
        assert response.status_code == 200
        
        search_results = response.get_json()
        assert 'results' in search_results
        
        # 3. Проверяем результаты поиска
        results = search_results['results']
        
        # Должен быть найден только 1 файл с совпадениями
        assert len(results) == 1, f"Ожидался 1 результат, получено {len(results)}"
        
        result = results[0]
        assert 'file_with_matches.txt' in result['filename']
        
        # Проверяем счётчик совпадений
        assert result['total'] == 2, f"Ожидалось 2 совпадения, получено {result['total']}"
        
        # Проверяем per_term
        assert len(result['per_term']) == 1, "Должен быть 1 термин"
        term_info = result['per_term'][0]
        assert term_info['term'] == 'монтаж'
        assert term_info['count'] == 2, f"Ожидалось 2 вхождения термина, получено {term_info['count']}"
        
        # 4. Проверяем статусы файлов
        files_state = FilesState(app.config['SEARCH_RESULTS_FILE'])
        
        # Файл с совпадениями должен быть зелёным
        file_with_matches_status = files_state.get_file_status(test_files['file_with_matches'])
        assert file_with_matches_status['status'] == 'contains_keywords'
        assert 'char_count' in file_with_matches_status
        assert file_with_matches_status['char_count'] > 0
        
        # Файл без совпадений должен быть жёлтым (no_keywords)
        file_without_matches_status = files_state.get_file_status(test_files['file_without_matches'])
        assert file_without_matches_status['status'] == 'no_keywords', \
            f"Файл без совпадений должен иметь статус 'no_keywords', получен '{file_without_matches_status.get('status')}'"
        assert 'char_count' in file_without_matches_status
        assert file_without_matches_status['char_count'] > 0
        
        # Ещё один файл без совпадений тоже должен быть жёлтым
        another_file_status = files_state.get_file_status(test_files['another_file'])
        assert another_file_status['status'] == 'no_keywords', \
            f"Файл без совпадений должен иметь статус 'no_keywords', получен '{another_file_status.get('status')}'"
        assert 'char_count' in another_file_status
        assert another_file_status['char_count'] > 0


def test_no_duplicates_in_search_results(client, app, test_files):
    """Тестирует отсутствие дублирования в результатах."""
    
    with app.app_context():
        # Строим индекс
        response = client.post('/build_index')
        assert response.status_code == 200
        
        # Выполняем поиск 
        response = client.post('/search',
                             json={'search_terms': 'монтаж'},
                             content_type='application/json')
        assert response.status_code == 200
        
        search_results = response.get_json()
        results = search_results['results']
        
        # Проверяем уникальность source в результатах
        sources = [r['source'] for r in results]
        unique_sources = set(sources)
        
        assert len(sources) == len(unique_sources), \
            f"Обнаружено дублирование в результатах: {sources}"


def test_files_json_endpoint(client, app, test_files):
    """Тестирует корректность эндпоинта /files_json."""
    
    with app.app_context():
        # Строим индекс и выполняем поиск
        client.post('/build_index')
        client.post('/search', 
                   json={'search_terms': 'монтаж'},
                   content_type='application/json')
        
        # Получаем список файлов
        response = client.get('/files_json')
        assert response.status_code == 200
        
        files_data = response.get_json()
        assert 'folders' in files_data
        assert 'file_statuses' in files_data
        
        file_statuses = files_data['file_statuses']
        
        # Проверяем, что все файлы имеют корректные статусы
        for file_path in [test_files['file_with_matches'], 
                         test_files['file_without_matches'], 
                         test_files['another_file']]:
            assert file_path in file_statuses, f"Файл {file_path} отсутствует в статусах"
            
            status = file_statuses[file_path]
            assert 'status' in status
            assert status['status'] in ['contains_keywords', 'no_keywords', 'error']
            
            if status['status'] in ['contains_keywords', 'no_keywords']:
                assert 'char_count' in status
                assert status['char_count'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])