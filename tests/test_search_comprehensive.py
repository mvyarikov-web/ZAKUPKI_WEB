"""
Комплексный тест поиска и отображения индекса.

Проверяет:
1. Правильный owner_id при индексации
2. Поиск возвращает корректные результаты с сниппетами
3. Подсветка ключевых слов в просмотре индекса
4. Визуальное оформление (синие заголовки, плейсхолдеры)
5. Интеграция поиска с UI
"""

import pytest
import os
import json
from webapp import create_app
from webapp.models.rag_models import RAGDatabase


@pytest.fixture
def app():
    """Создаём Flask приложение для тестов."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['USE_DATABASE'] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Заглушка для заголовков аутентификации."""
    return {'X-User-ID': '5'}  # Устанавливаем owner_id=5


@pytest.fixture
def db(app):
    """Подключение к БД."""
    with app.app_context():
        config = app.config
        # Формируем database_url из конфига или берём готовый
        database_url = config.get('DATABASE_URL')
        if not database_url:
            database_url = f"postgresql://{config.get('DB_USER', 'app_user')}:{config.get('DB_PASSWORD', 'change_me_strong')}@{config.get('DB_HOST', 'localhost')}:{config.get('DB_PORT', 5432)}/{config.get('DB_NAME', 'app_db')}"
        
        db = RAGDatabase(database_url)
        yield db
        # RAGDatabase не имеет метода close(), используем db.db.close()
        if hasattr(db, 'db') and hasattr(db.db, 'pool'):
            db.db.pool.closeall()


@pytest.fixture
def cleanup_test_data(db):
    """Очистка тестовых данных до и после теста."""
    # Не нужна очистка, так как используем существующие документы
    yield


def test_owner_id_in_chunks(client, db, auth_headers, cleanup_test_data):
    """
    Проблема 1: Проверка что owner_id=5 сохраняется в chunks.
    
    Тест:
    1. Загружаем файл под пользователем owner_id=5
    2. Строим индекс
    3. Проверяем что все чанки имеют owner_id=5
    """
    # Создаём тестовый файл
    test_content = "Тестовый документ про кондиционеры и вентиляцию."
    test_file = ('test_owner.txt', test_content.encode('utf-8'))
    
    # TODO: Реализовать middleware для обработки X-User-ID
    # Пока пропускаем этот тест, так как нужна интеграция с аутентификацией
    pytest.skip("Требуется middleware для X-User-ID")


def test_search_returns_matches_with_snippets(client, db, cleanup_test_data):
    """
    Проблема 2 и 3: Поиск возвращает результаты с контекстными сниппетами.
    
    Тест:
    1. Используем существующие документы в БД
    2. Ищем по ключевому слову "кондиционер"
    3. Проверяем что результаты содержат сниппеты с контекстом
    """
    # Проверяем, есть ли документы в БД
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM documents 
                WHERE owner_id = 1 AND is_visible = TRUE;
            """)
            doc_count = cur.fetchone()[0]
            
    if doc_count == 0:
        pytest.skip("Нет документов в БД для тестирования")
    
    # Выполняем поиск через API
    response = client.post('/search', 
                          json={'search_terms': 'кондиционер', 'exclude_mode': False},
                          content_type='application/json')
    
    assert response.status_code == 200
    data = response.get_json()
    
    # Проверяем результаты
    assert 'results' in data
    results = data['results']
    assert len(results) > 0, "Поиск должен вернуть результаты"
    
    # Проверяем первый результат
    first_result = results[0]
    assert 'file' in first_result
    assert 'match_count' in first_result
    assert first_result['match_count'] > 0, "Должны быть найдены совпадения"
    assert 'matches' in first_result
    assert len(first_result['matches']) > 0, "Должны быть matches с сниппетами"
    
    # Проверяем сниппеты
    first_match = first_result['matches'][0]
    assert 'snippet' in first_match, "Сниппет должен присутствовать"
    assert 'text' in first_match
    assert len(first_match['snippet']) > 0, "Сниппет не должен быть пустым"
    assert 'кондиционер' in first_match['snippet'].lower(), "Сниппет должен содержать искомое слово"


def test_index_view_highlighting(client, db, cleanup_test_data):
    """
    Проблема 4: Подсветка ключевых слов в просмотре индекса.
    
    Тест:
    1. Запрашиваем /view_index?q=кондиционер
    2. Проверяем наличие тегов <mark> в HTML
    """
    # Запрашиваем индекс с поиском
    response = client.get('/view_index?q=%D0%BA%D0%BE%D0%BD%D0%B4%D0%B8%D1%86%D0%B8%D0%BE%D0%BD%D0%B5%D1%80')
    
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    
    # Проверяем подсветку
    assert '<mark>' in html, "Должен быть тег <mark> для подсветки"
    assert '</mark>' in html
    assert 'кондиционер' in html.lower() or '\u043a\u043e\u043d\u0434\u0438\u0446\u0438\u043e\u043d\u0435\u0440' in html


def test_index_view_blue_headers(client, db, cleanup_test_data):
    """
    Проблема 5: Синие заголовки и отсутствие плейсхолдеров __LABEL__.
    
    Тест:
    1. Запрашиваем /view_index
    2. Проверяем наличие CSS-классов и отсутствие __LABEL__
    """
    # Запрашиваем индекс
    response = client.get('/view_index')
    
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    
    # Проверяем CSS-классы
    assert 'index-document-header' in html, "Должен быть класс для заголовков"
    assert 'index-document-label' in html, "Должен быть класс для меток"
    
    # Проверяем отсутствие плейсхолдеров
    assert '__LABEL__' not in html, "Не должно быть необработанных плейсхолдеров __LABEL__"
    assert '__HEADER__' not in html, "Не должно быть необработанных плейсхолдеров __HEADER__"
    assert '__/LABEL__' not in html
    assert '__/HEADER__' not in html
    
    # Проверяем наличие span-тегов с классами
    assert '<span class="index-document-label">' in html
    assert '<span class="index-document-header">' in html


def test_search_integration(client, db, cleanup_test_data):
    """
    Интеграционный тест: полный цикл поиска.
    
    Тест:
    1. Выполняем поиск по "кондиционер"
    2. Проверяем результаты
    3. Открываем просмотр индекса с подсветкой
    """
    # Поиск по "кондиционер"
    response = client.post('/search',
                          json={'search_terms': 'кондиционер', 'exclude_mode': False},
                          content_type='application/json')
    
    assert response.status_code == 200
    data = response.get_json()
    results = data['results']
    
    # Должны найтись документы
    assert len(results) >= 1, f"Должен быть найден минимум 1 документ, получено {len(results)}"
    
    # Проверяем сниппеты
    for result in results:
        assert result['match_count'] > 0
        assert len(result['matches']) > 0
        for match in result['matches']:
            assert 'snippet' in match
            assert 'кондиционер' in match['snippet'].lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
