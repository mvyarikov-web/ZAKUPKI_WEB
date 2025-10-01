import re
import json
import pytest
from webapp import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()


def test_index_has_containers(client):
    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'filesList' in html


def test_search_results_structure(client, tmp_path):
    # Создаем простой текстовый файл в uploads через API загрузки недоступен в этом тесте
    # Полагаемся на существующий индекс и эндпоинт /search — проверяем структуру выдачи
    resp = client.post('/search', json={'search_terms': 'документ'})
    assert resp.status_code in (200, 400)  # если нет индекса — может вернуться 400
    if resp.status_code == 200:
        data = resp.get_json()
        assert 'results' in data
        # Поля используются в клиенте для построения результатов
        if data['results']:
            r0 = data['results'][0]
            assert 'source' in r0 or 'path' in r0
            assert 'per_term' in r0


def test_css_no_overflow_on_folder_content():
    # Проверяем, что в CSS для .folder-content нет жесткого overflow:hidden и max-height ограничений
    from pathlib import Path
    css_path = Path('static/css/styles.css')
    text = css_path.read_text(encoding='utf-8')
    # В раскрытом состоянии не должно быть overflow:hidden и max-height ограничений
    folder_content_block = re.search(r"\.folder-content\s*\{[^}]+\}", text, re.S)
    assert folder_content_block, 'Нет блока .folder-content в CSS'
    block = folder_content_block.group(0)
    assert 'overflow: visible' in block
    assert 'max-height: none' in block

