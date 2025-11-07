import io
import pytest


def test_upload_requires_user_id_when_strict(client, monkeypatch, tmp_path):
    # Включаем строгий режим
    monkeypatch.setenv('STRICT_USER_ID', 'true')

    # Готовим временный файл в uploads через тестовый клиент
    file_stream = io.BytesIO(b"hello world")
    data = {'files': (file_stream, 'a.txt')}
    resp = client.post('/upload', data=data, content_type='multipart/form-data')
    assert resp.status_code == 400
    assert 'пользователя' in resp.get_json().get('error', '').lower()


def test_upload_ok_with_user_id_when_strict(client, monkeypatch, tmp_path):
    monkeypatch.setenv('STRICT_USER_ID', 'true')

    # Тестовый файл
    file_stream = io.BytesIO(b"hello world 2")
    data = {'files': (file_stream, 'b.txt')}
    resp = client.post('/upload', headers={'X-User-ID': '5'}, data=data, content_type='multipart/form-data')
    # Может быть 200 даже если индексация отключена — нас интересует отсутствие 400
    assert resp.status_code in (200, 201)


def test_search_requires_user_id_when_strict(client, monkeypatch):
    monkeypatch.setenv('STRICT_USER_ID', 'true')

    resp = client.post('/search', json={'keywords': ['тест']})
    assert resp.status_code == 400
    assert 'пользователя' in resp.get_json().get('error', '').lower()


def test_view_requires_user_id_when_strict(client, monkeypatch):
    monkeypatch.setenv('STRICT_USER_ID', 'true')

    resp = client.get('/view/some.txt')
    assert resp.status_code == 400
    assert 'пользователя' in resp.get_json().get('error', '').lower()