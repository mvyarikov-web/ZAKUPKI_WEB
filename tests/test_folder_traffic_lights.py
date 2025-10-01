"""
Проверка светофоров внутри обычной папки на самих файлах:
- зелёный: есть совпадения
- жёлтый: файл прочитан, но совпадений нет
- красный: файл с нулевым количеством символов (ошибка/не прочитан)

Тест использует эндпоинты /build_index, /search и /files_json, а также FilesState.
"""
import os
import tempfile
import json
import pytest

from webapp import create_app
from webapp.services.state import FilesState


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    app.config['INDEX_FOLDER'] = tempfile.mkdtemp()
    app.config['SEARCH_RESULTS_FILE'] = os.path.join(app.config['INDEX_FOLDER'], 'search_results.json')
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def regular_folder_setup(app):
    uploads = app.config['UPLOAD_FOLDER']
    folder = os.path.join(uploads, 'regular')
    os.makedirs(folder, exist_ok=True)

    # 1) Файл с совпадениями (зелёный)
    green_path = os.path.join(folder, 'green.txt')
    with open(green_path, 'w', encoding='utf-8') as f:
        f.write('Ключевое слово монтаж. Ещё раз: монтаж.')

    # 2) Файл без совпадений (жёлтый)
    yellow_path = os.path.join(folder, 'yellow.txt')
    with open(yellow_path, 'w', encoding='utf-8') as f:
        f.write('Обычный текст без ключевых слов.')

    # 3) Файл, который станет красным: создадим пустой и симулируем char_count=0 через индексацию
    red_path = os.path.join(folder, 'red.txt')
    with open(red_path, 'w', encoding='utf-8') as f:
        f.write('')

    return {
        'folder': folder,
        'green': 'regular/green.txt',
        'yellow': 'regular/yellow.txt',
        'red': 'regular/red.txt',
    }


def test_folder_file_statuses(client, app, regular_folder_setup):
    with app.app_context():
        # 1) Соберём индекс
        r = client.post('/build_index')
        assert r.status_code == 200

        # 2) Выполним поиск по "монтаж" — это окрасит green в contains_keywords
        r = client.post('/search', json={'search_terms': 'монтаж'}, content_type='application/json')
        assert r.status_code == 200

        # 3) Получим статусы файлов
        fs = FilesState(app.config['SEARCH_RESULTS_FILE'])
        st_green = fs.get_file_status(regular_folder_setup['green'])
        st_yellow = fs.get_file_status(regular_folder_setup['yellow'])
        st_red = fs.get_file_status(regular_folder_setup['red'])

        # Зелёный файл: найдено
        assert st_green.get('status') == 'contains_keywords'
        assert st_green.get('char_count', 0) > 0

        # Жёлтый файл: прочитан, совпадений нет
        assert st_yellow.get('status') == 'no_keywords'
        assert st_yellow.get('char_count', 0) > 0

        # Красный файл: должен иметь char_count == 0 и статус error
        assert st_red.get('char_count', 0) == 0
        assert st_red.get('status') == 'error'

        # 4) Проверим JSON дерева файлов
        r = client.get('/files_json')
        assert r.status_code == 200
        data = r.get_json()
        assert 'folders' in data and 'file_statuses' in data

        fstat = data['file_statuses']
        for key in (regular_folder_setup['green'], regular_folder_setup['yellow'], regular_folder_setup['red']):
            assert key in fstat, f"Нет статуса для {key}"

        assert fstat[regular_folder_setup['green']]['status'] == 'contains_keywords'
        assert fstat[regular_folder_setup['yellow']]['status'] == 'no_keywords'
        # Красный подтверждаем по status/error или по нулевому char_count
        assert fstat[regular_folder_setup['red']]['status'] in ('error', 'unsupported')
        assert fstat[regular_folder_setup['red']].get('char_count', 0) == 0
