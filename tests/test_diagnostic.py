"""
Диагностический тест для анализа проблем со счётчиками и статусами.
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
    
    # Файл с совпадениями - точно 2 вхождения слова "монтаж"
    with open(os.path.join(regular_folder, 'file_with_matches.txt'), 'w', encoding='utf-8') as f:
        f.write('Это тестовый файл с ключевым словом монтаж. Монтаж выполняется качественно.')
    
    # Файл без совпадений  
    with open(os.path.join(regular_folder, 'file_without_matches.txt'), 'w', encoding='utf-8') as f:
        f.write('Это обычный текстовый файл без искомых слов. Здесь только обычная информация.')
    
    return {
        'regular_folder': regular_folder,
        'file_with_matches': 'regular_folder/file_with_matches.txt',
        'file_without_matches': 'regular_folder/file_without_matches.txt'
    }


def test_diagnostic_search_and_statuses(client, app, test_files):
    """Диагностический тест для анализа проблем."""
    
    with app.app_context():
        print(f"\n=== ДИАГНОСТИКА ПРОБЛЕМ ===")
        
        # 1. Строим индекс
        print("1. Строим индекс...")
        response = client.post('/build_index')
        assert response.status_code == 200
        
        # 2. Выполняем поиск
        print("2. Выполняем поиск по слову 'монтаж'...")
        response = client.post('/search', 
                             json={'search_terms': 'монтаж'},
                             content_type='application/json')
        assert response.status_code == 200
        
        search_results = response.get_json()
        results = search_results['results']
        
        print(f"Количество результатов: {len(results)}")
        
        for i, result in enumerate(results):
            print(f"\nРезультат {i+1}:")
            print(f"  Filename: {result['filename']}")
            print(f"  Source: {result['source']}")
            print(f"  Total: {result['total']}")
            print(f"  Per term:")
            for term_info in result['per_term']:
                print(f"    Term: '{term_info['term']}', Count: {term_info['count']}")
                print(f"    Snippets: {term_info['snippets']}")
        
        # 3. Проверяем статусы файлов
        print(f"\n3. Проверяем статусы файлов...")
        files_state = FilesState(app.config['SEARCH_RESULTS_FILE'])
        
        all_statuses = files_state.get_file_status()
        print(f"Общее количество файлов в статусах: {len(all_statuses)}")
        
        for file_path, status in all_statuses.items():
            print(f"\nФайл: {file_path}")
            print(f"  Status: {status.get('status', 'unknown')}")
            print(f"  Char count: {status.get('char_count', 'unknown')}")
            if 'found_terms' in status:
                print(f"  Found terms: {status['found_terms']}")
        
        # 4. Читаем индекс напрямую
        print(f"\n4. Проверяем содержимое индекса...")
        index_path = os.path.join(app.config['INDEX_FOLDER'], '_search_index.txt')
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            print(f"Индекс содержит {len(lines)} строк")
            for i, line in enumerate(lines[:20]):  # Показываем первые 20 строк
                print(f"  {i+1}: {line.strip()}")
        else:
            print("Индекс не найден")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])