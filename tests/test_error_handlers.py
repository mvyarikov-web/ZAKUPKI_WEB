"""
Тесты для обработчиков ошибок Flask.

Проверяет, что обработчики 404/500/413 работают корректно
даже при отсутствии шаблонов error.html/404.html/500.html.
"""


def test_404_handler_returns_fallback_html(client):
    """Проверка, что 404 возвращает fallback HTML при отсутствии шаблонов."""
    response = client.get('/nonexistent-route-for-testing')
    
    assert response.status_code == 404
    assert b'404' in response.data
    assert b'Page not found' in response.data or b'\xd0\xa1\xd1\x82\xd1\x80\xd0\xb0\xd0\xbd\xd0\xb8\xd1\x86\xd0\xb0 \xd0\xbd\xd0\xb5 \xd0\xbd\xd0\xb0\xd0\xb9\xd0\xb4\xd0\xb5\xd0\xbd\xd0\xb0' in response.data  # Страница не найдена


def test_404_handler_returns_json_for_api(client):
    """Проверка, что 404 возвращает JSON для API роутов."""
    response = client.get('/api/nonexistent-endpoint')
    
    assert response.status_code == 404
    assert response.is_json
    data = response.get_json()
    assert 'error' in data
    assert 'не найден' in data['error'].lower() or 'not found' in data['error'].lower()


def test_health_endpoint_still_works(client):
    """Проверка, что /health работает после изменений в обработчиках ошибок."""
    response = client.get('/health')
    
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data.get('status') == 'ok'
