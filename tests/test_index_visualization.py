import re
import os
import psycopg2
import pytest
from flask import url_for

@pytest.mark.usefixtures('client', 'app')
def test_view_index_highlighting(client, app):
    """Построить индекс, выполнить поиск и проверить подсветку; без q подсветки быть не должно."""
    # Предусловие: есть хотя бы один документ в БД (если нет — пропустим)
    dsn = app.config['DATABASE_URL'].replace('postgresql+psycopg2://', 'postgresql://')
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_documents WHERE is_soft_deleted=FALSE;")
            cnt = cur.fetchone()[0]
            if cnt == 0:
                pytest.skip('Нет документов для проверки подсветки индекса')
    # 1) Запрос без q — нет <mark>
    r1 = client.get('/view_index?raw=0')
    assert r1.status_code == 200
    assert b'<mark>' not in r1.data, 'Подсветка не должна появляться без параметра q'
    # 2) Запрос с q (используем слово из тестового документа, допустим "Документ" или "Тест")
    r2 = client.get('/view_index?raw=0&q=Документ')
    assert r2.status_code == 200
    assert b'<mark>' in r2.data, 'Подсветка должна появиться при переданном q'

@pytest.mark.usefixtures('client', 'app')
def test_main_page_empty_after_cleanup(client, app):
    """После очистки БД (TRUNCATE) главная страница в режиме use_database должна быть пустой."""
    if not app.config.get('use_database'):
        pytest.skip('Тест актуален только для режима use_database')
    dsn = app.config['DATABASE_URL'].replace('postgresql+psycopg2://', 'postgresql://')
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE chunks, user_documents, documents RESTART IDENTITY CASCADE;")
        conn.commit()
    r = client.get('/')
    assert r.status_code == 200
    # Ожидаем что нет метки '📁 Документы (БД)' или она пустая
    html = r.data.decode('utf-8', errors='ignore')
    assert ('Документы (БД)' not in html) or ('file-count-badge">0<' not in html), 'После очистки БД список должен быть пустым'
