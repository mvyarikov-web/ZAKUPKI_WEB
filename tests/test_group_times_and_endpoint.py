import os
import json
import time
import pytest


@pytest.mark.timeout(30)
def test_group_times_populated_with_durations(tmp_path):
    """Проверяет, что status.json заполняется реальным временем по группам
    (fast/medium/slow) и что длительности >= заданных задержек.
    """
    from document_processor.search.indexer import Indexer

    # Готовим структуру: parent/{uploads,index}
    parent = tmp_path / "root"
    uploads = parent / "uploads"
    index_dir = parent / "index"
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    # Создаём набор файлов: fast (txt), medium (docx), slow (zip)
    (uploads / "a_fast.txt").write_text("fast", encoding="utf-8")
    # Для medium создадим простой docx-заглушку как zip, чтобы не вызывать docx-парсер
    import zipfile
    with zipfile.ZipFile(uploads / "b_medium.docx", 'w') as z:
        z.writestr("[Content_Types].xml", "<Types></Types>")
    with zipfile.ZipFile(uploads / "c_slow.zip", 'w') as z:
        z.writestr("inside.txt", "content")

    # Патчим _process_group: имитируем задержку и упрощённый вывод во временный файл
    idx = Indexer()
    original_process = idx._process_group

    delays = {"fast": 1, "medium": 2, "slow": 3}  # секунды

    def fake_process(group_files, temp_file, group_name):
        t = delays.get(group_name, 0)
        time.sleep(t)
        # минимальный валидный вывод для вставки в индекс
        with open(temp_file, 'w', encoding='utf-8') as f:
            for p in group_files:
                f.write("===== FILE: " + os.path.basename(p) + "\n")
                f.write("TEXT\n\n")

    idx._process_group = fake_process  # type: ignore

    try:
        idx.create_index(str(uploads), use_groups=True)
    finally:
        # возвращаем оригинал на всякий случай
        idx._process_group = original_process  # type: ignore

    # Проверяем status.json
    status_path = index_dir / "status.json"
    assert status_path.exists(), "status.json должен существовать"
    status = json.loads(status_path.read_text(encoding='utf-8'))

    assert status.get('status') == 'completed'
    gs = status.get('group_status') or {}
    assert gs.get('fast') == 'completed'
    assert gs.get('medium') == 'completed'
    assert gs.get('slow') == 'completed'

    gt = status.get('group_times') or {}
    # проверяем, что длительности присутствуют и не меньше заданных задержек (округление до сек)
    assert int(gt.get('fast', {}).get('duration_sec', -1)) >= delays['fast']
    assert int(gt.get('medium', {}).get('duration_sec', -1)) >= delays['medium']
    assert int(gt.get('slow', {}).get('duration_sec', -1)) >= delays['slow']

    # Дополнительно: порядок по величине (обычно slow >= medium >= fast)
    assert gt['slow']['duration_sec'] >= gt['medium']['duration_sec'] >= gt['fast']['duration_sec']


@pytest.mark.timeout(30)
def test_index_status_endpoint_includes_group_times(tmp_path):
    """Проверяет, что /index_status возвращает group_times и статусы групп
    после построения индекса с группами.
    """
    from document_processor.search.indexer import Indexer
    from webapp import create_app

    # Структура
    parent = tmp_path / "root"
    uploads = parent / "uploads"
    index_dir = parent / "index"
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    # Файлы для всех групп
    (uploads / "a.txt").write_text("fast", encoding='utf-8')
    import zipfile
    with zipfile.ZipFile(uploads / "b.docx", 'w') as z:
        z.writestr("[Content_Types].xml", "<Types></Types>")
    with zipfile.ZipFile(uploads / "c.zip", 'w') as z:
        z.writestr("inside.txt", "content")

    # Патчим процесс, чтобы не зависеть от внешних либ и ускорить
    idx = Indexer()
    original_process = idx._process_group

    def fast_fake_process(group_files, temp_file, group_name):
        # Быстрый минимальный вывод без сна
        with open(temp_file, 'w', encoding='utf-8') as f:
            for p in group_files:
                f.write("===== FILE: " + os.path.basename(p) + "\n")
                f.write("TEXT\n\n")

    idx._process_group = fast_fake_process  # type: ignore
    try:
        idx.create_index(str(uploads), use_groups=True)
    finally:
        idx._process_group = original_process  # type: ignore

    # Flask-приложение для вызова /index_status
    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)

    with app.test_client() as client:
        resp = client.get('/index_status')
        assert resp.status_code == 200
        data = resp.get_json()

        assert data.get('exists') is True
        assert data.get('index_exists') is True
        assert data.get('status') in ('completed', 'idle')  # completed ожидаемо

        # Наличие и структура полей групп
        assert 'group_status' in data
        assert 'group_times' in data
        for g in ('fast', 'medium', 'slow'):
            assert g in data['group_status']
            assert g in data['group_times']
            # duration_sec может быть 0 при очень быстрой вставке — это валидно
            assert 'duration_sec' in data['group_times'][g] or (
                'started_at' in data['group_times'][g] and 'completed_at' in data['group_times'][g]
            )
