"""Тесты AI анализа в режиме DB-first."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def enable_db_mode(app):
    """Включить режим БД для каждого теста."""
    app.config['use_database'] = True
    yield


def _patch_common(monkeypatch, fetch_result):
    """Заготовка общих подстановок для хендлеров."""
    monkeypatch.setattr('webapp.routes.ai_analysis._get_db', lambda: object())
    monkeypatch.setattr('webapp.routes.ai_analysis._required_user_id', lambda: 1)
    monkeypatch.setattr('webapp.routes.ai_analysis._fetch_documents_from_db', lambda db, owner_id, paths: fetch_result(paths))


def test_get_text_size_returns_metrics(auth_client, monkeypatch):
    """Подсчёт размера текста берёт данные из БД и возвращает метрики."""
    combined = "=== doc.txt ===\nСодержимое"
    prompt = "Запрос"

    def fake_fetch(paths):
        assert paths == ['doc.txt']
        return combined, [{'path': 'doc.txt', 'text': 'Содержимое', 'length': len('Содержимое')}], []

    _patch_common(monkeypatch, fake_fetch)

    response = auth_client.post('/ai_analysis/get_text_size', json={'file_paths': ['doc.txt'], 'prompt': prompt})
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['text_size'] == len(combined)
    assert data['prompt_size'] == len(prompt)
    assert data['total_size'] == len(combined) + len(prompt) + 2


def test_get_text_size_reports_missing_files(auth_client, monkeypatch):
    """Если документы не найдены, возвращается 404 с сообщением."""

    def fake_fetch(paths):
        assert paths == ['missing.docx']
        return '', [], ['missing.docx']

    _patch_common(monkeypatch, fake_fetch)

    response = auth_client.post('/ai_analysis/get_text_size', json={'file_paths': ['missing.docx'], 'prompt': 'x'})
    assert response.status_code == 404
    data = response.get_json()
    assert data['success'] is False
    assert 'не найдены' in data['message'].lower()


def test_analyze_uses_override_and_validates_access(auth_client, monkeypatch):
    """При передаче override_text проверяется доступ к документам и выполняется анализ."""
    calls = {'checked': False}

    def fake_fetch(paths):
        calls['checked'] = True
        return '', [], []

    _patch_common(monkeypatch, fake_fetch)

    class DummyService:
        def analyze_text(self, combined_text: str, prompt: str, max_request_size: int):
            assert combined_text == 'Готовый текст'
            assert prompt == 'Проверка'
            return True, 'ok', 'Ответ'

    monkeypatch.setattr('webapp.routes.ai_analysis.GPTAnalysisService', lambda: DummyService())

    response = auth_client.post(
        '/ai_analysis/analyze',
        json={
            'file_paths': ['doc.txt'],
            'prompt': 'Проверка',
            'max_request_size': 4096,
            'override_text': 'Готовый текст'
        }
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['response'] == 'Ответ'
    assert calls['checked'] is True


def test_analyze_returns_404_when_documents_missing(auth_client, monkeypatch):
    """При отсутствии документов эндпоинт сообщает об этом."""

    def fake_fetch(paths):
        return '', [], ['bad.txt']

    _patch_common(monkeypatch, fake_fetch)

    response = auth_client.post(
        '/ai_analysis/analyze',
        json={'file_paths': ['bad.txt'], 'prompt': 'Тест'}
    )
    assert response.status_code == 404
    data = response.get_json()
    assert data['success'] is False
    assert 'не найдены' in data['message'].lower()


def test_get_texts_returns_docs_from_db(auth_client, monkeypatch):
    """Возврат текстов опирается на БД и повторяет структуру fetch."""

    documents = [
        {'path': 'doc1.txt', 'text': 'A', 'length': 1},
        {'path': 'doc2.txt', 'text': 'B', 'length': 1},
    ]

    def fake_fetch(paths):
        return '=== combined ===', documents, []

    _patch_common(monkeypatch, fake_fetch)

    response = auth_client.post('/ai_analysis/get_texts', json={'file_paths': ['doc1.txt', 'doc2.txt']})
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['docs'] == documents
