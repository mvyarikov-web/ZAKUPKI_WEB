"""Тесты базовых HTTP эндпоинтов для шага 1 чек-листа инкремента 18."""
from __future__ import annotations

from flask import Response


def test_health_endpoint_returns_ok(auth_client) -> None:
    """/health должен возвращать 200 и JSON со статусом ok."""
    response: Response = auth_client.get('/health')
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert payload.get('status') == 'ok'


def test_index_page_contains_required_controls(auth_client) -> None:
    """Главная страница должна содержать кнопки перестроения и просмотра индекса."""
    response: Response = auth_client.get('/')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'id="rebuildIndexBtn"' in html
    assert 'Перестроить индекс' in html
    assert 'id="viewIndexBtn"' in html
    assert 'Просмотр индекса' in html
    assert 'href="/view_index"' in html
