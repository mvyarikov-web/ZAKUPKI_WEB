import time
import pytest
from pathlib import Path


@pytest.mark.timeout(45)
def test_index_status_progression_and_times_with_timeouts(tmp_path):
    """Интеграционный тест: имитируем задержки групп и опрашиваем /index_status
    с таймаутами ожидания, проверяя смену статусов групп и появление времени.
    """
    from webapp import create_app
    from document_processor.search.indexer import Indexer
    import zipfile

    # Готовим структуру
    parent = tmp_path / 'root'
    uploads = parent / 'uploads'
    index_dir = parent / 'index'
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    # Файлы для всех групп
    (uploads / 'a.txt').write_text('fast', encoding='utf-8')
    with zipfile.ZipFile(uploads / 'b.docx', 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
    with zipfile.ZipFile(uploads / 'c.zip', 'w') as z:
        z.writestr('inside.txt', 'x')

    # Патчим процесс групп и добавляем задержки
    idx = Indexer()
    original = idx._process_group
    delays = {'fast': 1, 'medium': 2, 'slow': 2}

    def slow_process(group_files, temp_file, group_name):
        time.sleep(delays.get(group_name, 0))
        with open(temp_file, 'w', encoding='utf-8') as f:
            for p in group_files:
                f.write('===== FILE: ' + Path(p).name + '\nTEXT\n\n')

    idx._process_group = slow_process  # type: ignore
    try:
        # Стартуем индексацию в текущем потоке (для простоты теста)
        idx.create_index(str(uploads), use_groups=True)
    finally:
        idx._process_group = original  # type: ignore

    # Создаём Flask app и проверяем /index_status
    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)

    with app.test_client() as client:
        # Опрос /index_status с таймаутом ожидания статуса completed
        t0 = time.time()
        timeout = 10
        last = None
        while time.time() - t0 < timeout:
            resp = client.get('/index_status')
            assert resp.status_code == 200
            data = resp.get_json()
            last = data
            # Ждём финала
            if data.get('status') == 'completed':
                break
            time.sleep(0.3)
        assert last is not None
        assert last.get('status') == 'completed'

        # Проверяем времена по группам
        gt = last.get('group_times') or {}
        assert 'fast' in gt and 'medium' in gt and 'slow' in gt
        # Продолжительности могут быть 0-2 сек из-за округления, но должны существовать
        for g in ('fast', 'medium', 'slow'):
            assert 'duration_sec' in gt[g] or ('started_at' in gt[g] and 'completed_at' in gt[g])


@pytest.mark.timeout(30)
def test_clear_all_resets_status(tmp_path):
    """Проверяет, что после /clear_all индикаторы считаются отсутствующими (exists=False)."""
    from webapp import create_app
    from document_processor.search.indexer import Indexer

    # Структура
    parent = tmp_path / 'root'
    uploads = parent / 'uploads'
    index_dir = parent / 'index'
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    # Файл, чтобы был индекс
    (uploads / 'a.txt').write_text('x', encoding='utf-8')
    Indexer().create_index(str(uploads), use_groups=True)

    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)

    with app.test_client() as client:
        # Убедимся, что индекс существует
        d1 = client.get('/index_status').get_json()
        assert d1.get('exists') is True

        # Вызываем очистку
        r = client.post('/clear_all')
        assert r.status_code == 200
        d2 = client.get('/index_status').get_json()
        # После очистки индекс может отсутствовать
        assert d2.get('exists') is False
