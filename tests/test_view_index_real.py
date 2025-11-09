import os
import pytest

pytestmark = pytest.mark.skipif(not os.path.exists('uploads'), reason='Нет папки uploads с реальными файлами')


@pytest.fixture
def app():
    from webapp import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['use_database'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_view_index_contains_documents(client):
    """Проверяет, что /view_index содержит группы и документы (DB-first).
    Тест не передаёт X-User-ID намеренно: fallback внутри view_index должен выставить owner_id=1."""
    resp = client.get('/view_index?raw=1')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    # Проверяем наличие групп (только в raw режиме)
    assert '[ГРУППА:' in text, 'Не найдены группы индекса (raw=1)'
    # После рендеринга плейсхолдеры заменяются на span с классами
    assert 'index-document-header' in text or 'index-document-label' in text, 'Нет рендеринга заголовков/меток документа'
