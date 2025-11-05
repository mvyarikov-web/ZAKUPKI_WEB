"""Тест отображения результатов поиска под файлами"""
import pytest
from webapp import create_app


@pytest.fixture
def app():
    """Создаём Flask приложение для тестирования"""
    test_app = create_app()
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):
    """Клиент для тестирования"""
    return app.test_client()


def test_search_returns_per_term_structure(client, tmp_path):
    """Тест, что поиск возвращает правильную структуру per_term для JavaScript"""
    # Создаём тестовый файл
    test_file = tmp_path / "test.txt"
    test_file.write_text("Это тестовый документ с ключевыми словами: тест, документ, слова")
    
    # Загружаем файл
    with open(test_file, 'rb') as f:
        response = client.post('/upload', data={
            'files': [(f, 'test.txt')]
        })
    assert response.status_code == 200
    
    # Выполняем поиск
    response = client.post('/search', 
                          json={'search_terms': 'тест, документ'})
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'results' in data
    assert len(data['results']) > 0
    
    # Проверяем структуру результата
    result = data['results'][0]
    print(f"Search result structure: {result}")
    
    # Должны быть поля для JavaScript
    assert 'source' in result or 'path' in result
    assert 'per_term' in result
    assert isinstance(result['per_term'], list)
    
    if result['per_term']:
        term_entry = result['per_term'][0]
        assert 'term' in term_entry
        assert 'count' in term_entry
        assert 'snippets' in term_entry
        assert isinstance(term_entry['snippets'], list)


def test_html_contains_search_result_containers(client):
    """Тест, что HTML содержит контейнеры для результатов поиска"""
    response = client.get('/')
    assert response.status_code == 200
    
    html_content = response.get_data(as_text=True)
    
    # Проверяем наличие нужных классов в HTML
    assert 'file-item-wrapper' in html_content
    assert 'file-search-results' in html_content
    assert 'data-file-path' in html_content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])