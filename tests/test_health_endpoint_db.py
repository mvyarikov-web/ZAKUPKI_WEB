import os
import json
import pytest
from webapp import create_app


@pytest.mark.smoke
def test_health_endpoint_basic():
    """Проверка, что /health отвечает 200 и возвращает JSON.
    В этой версии эндпоинт минимален и возвращает {"status":"ok"}.
    """
    app = create_app('testing')
    with app.test_client() as client:
        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert data.get('status') == 'ok'
