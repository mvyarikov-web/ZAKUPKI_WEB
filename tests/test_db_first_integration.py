"""
Интеграционный тест DB-first индексации и визуализации.

Проверяет:
1. Реальные таблицы БД заполняются при индексации
2. Сводный индекс строится из БД при /view_index
3. Индекс визуализируется корректно
4. Файлы доступны через /view/<storage_url>

Использует реальные файлы из uploads/.
"""
import pytest
import os
import json
from flask import Flask


@pytest.fixture
def app():
    """Создаёт тестовое приложение с DB-first конфигурацией."""
    from webapp import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    # Убеждаемся что БД включена
    app.config['use_database'] = True
    yield app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Подключение к БД."""
    from webapp.models.rag_models import RAGDatabase
    with app.app_context():
        db = RAGDatabase()
        yield db


def get_owner_id(app):
    """Получить тестового пользователя (admin = 5)."""
    return 5


def test_01_db_tables_exist(db):
    """Проверка существования таблиц documents и chunks."""
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            # Проверяем таблицу documents
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'documents'
                );
            """)
            assert cur.fetchone()[0], "Таблица documents не найдена"
            
            # Проверяем таблицу chunks
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'chunks'
                );
            """)
            assert cur.fetchone()[0], "Таблица chunks не найдена"


def test_02_check_uploaded_files_exist(app):
    """Проверка наличия реальных файлов в uploads/."""
    uploads = app.config['UPLOAD_FOLDER']
    test_folder = os.path.join(uploads, 'Тестовая выборка AI Анализ')
    
    # Проверяем, что папка существует
    assert os.path.exists(test_folder), f"Папка {test_folder} не найдена"
    
    # Проверяем наличие хотя бы одного .docx файла
    files = [f for f in os.listdir(test_folder) if f.endswith('.docx')]
    assert len(files) > 0, f"В папке {test_folder} нет .docx файлов"
    
    print(f"✅ Найдено {len(files)} файлов для тестирования")


def test_03_build_index_db(client, app, db):
    """Тест построения индекса в БД через /build_index."""
    # Очищаем БД перед тестом
    owner_id = get_owner_id(app)
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            # Удаляем связи пользователя и глобальные документы (упрощённо: полный сброс видимости)
            cur.execute("DELETE FROM user_documents WHERE user_id = %s;", (owner_id,))
        conn.commit()
    
    # Вызываем /build_index
    response = client.post('/build_index', headers={'X-User-ID': str(owner_id)})
    assert response.status_code == 200, f"Ошибка построения индекса: {response.data}"
    
    data = response.get_json()
    assert data['success'], f"build_index вернул success=False: {data.get('message')}"
    
    # Проверяем статистику
    stats = data.get('stats', {})
    print(f"✅ Индексация завершена: {stats}")
    
    # В новой модели глобального дедупа indexed_documents может быть 0 (если документы уже были глобально)
    # Проверяем, что после индексации у пользователя появились связи user_documents
    if stats.get('indexed_documents', 0) == 0:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_documents WHERE user_id = %s AND is_soft_deleted = FALSE;", (owner_id,))
                assert cur.fetchone()[0] > 0, "После индексации у пользователя нет доступных документов"
    else:
        assert stats.get('indexed_documents', 0) > 0


def test_04_verify_documents_in_db(db, app):
    """Проверка, что документы записались в БД."""
    owner_id = get_owner_id(app)
    
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            # Считаем документы
            cur.execute("""
                SELECT COUNT(*) FROM user_documents 
                WHERE user_id = %s AND is_soft_deleted = FALSE;
            """, (owner_id,))
            docs_count = cur.fetchone()[0]
            
            assert docs_count > 0, "В БД нет документов после индексации"
            print(f"✅ Документов в БД: {docs_count}")
            
            # Получаем примеры документов
            cur.execute("""
                SELECT d.id, COALESCE(ud.original_filename, d.sha256), ud.user_path 
                FROM user_documents ud
                JOIN documents d ON d.id = ud.document_id
                WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
                LIMIT 3;
            """, (owner_id,))
            docs = cur.fetchall()
            
            for doc_id, filename, storage_url in docs:
                print(f"  - doc#{doc_id}: {filename} → {storage_url}")


def test_05_verify_chunks_in_db(db, app):
    """Проверка, что чанки записались в БД."""
    owner_id = get_owner_id(app)
    
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            # Считаем чанки
            cur.execute("""
                SELECT COUNT(*) FROM chunks c
                WHERE c.document_id IN (
                    SELECT document_id FROM user_documents WHERE user_id = %s AND is_soft_deleted = FALSE
                );
            """, (owner_id,))
            chunks_count = cur.fetchone()[0]
            
            assert chunks_count > 0, "В БД нет чанков после индексации"
            print(f"✅ Чанков в БД: {chunks_count}")
            
            # Получаем примеры чанков с текстом
            cur.execute("""
                SELECT c.id, c.document_id, c.chunk_idx, 
                       LEFT(c.text, 100) as text_preview,
                       COALESCE(ud.original_filename, d.sha256)
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN user_documents ud ON ud.document_id = d.id AND ud.user_id = %s AND ud.is_soft_deleted = FALSE
                ORDER BY c.document_id, c.chunk_idx
                LIMIT 3;
            """, (owner_id,))
            chunks = cur.fetchall()
            
            for chunk_id, doc_id, chunk_idx, text_preview, filename in chunks:
                print(f"  - chunk#{chunk_id} doc#{doc_id}[{chunk_idx}] ({filename}): {text_preview}...")


def test_06_index_status_shows_db_data(client, app):
    """Проверка, что /index_status возвращает информацию из БД."""
    # Строгий режим требует X-User-ID
    owner_id = get_owner_id(app)
    response = client.get('/index_status', headers={'X-User-ID': str(owner_id)})
    assert response.status_code == 200
    
    data = response.get_json()
    assert data.get('index_exists'), "index_exists должен быть True после индексации"
    assert data.get('entries', 0) > 0, "entries (количество документов) должно быть > 0"
    
    # Проверяем DB-сводку
    db_info = data.get('db', {})
    assert db_info.get('documents', 0) > 0, "db.documents должно быть > 0"
    
    print(f"✅ /index_status: {data.get('entries')} документов")


def test_07_view_index_builds_from_db(client, app):
    """Проверка, что /view_index строит индекс из БД."""
    owner_id = get_owner_id(app)
    response = client.get('/view_index', headers={'X-User-ID': str(owner_id)})
    assert response.status_code == 200
    
    content = response.data.decode('utf-8')
    
    # Проверяем наличие структуры индекса
    assert 'ГРУППА: FAST' in content or 'ГРУППА: MEDIUM' in content, \
        "Индекс не содержит групп"
    
    # Проверяем наличие заголовков документов
    assert 'ЗАГОЛОВОК:' in content, "Индекс не содержит заголовков документов"
    
    # Проверяем наличие реального текста (не только заголовки)
    lines = [l for l in content.split('\n') if l.strip()]
    # Должны быть строки-данные, отличные от служебных заголовков
    has_real_content = any(('ЗАГОЛОВОК:' not in l and 'ГРУППА:' not in l and 'Файлов:' not in l) for l in lines)
    assert has_real_content, "Индекс не содержит реального текста документов"
    
    print("✅ /view_index строит сводный индекс из БД с реальным контентом")


def test_08_view_file_by_storage_url(client, app, db):
    """Проверка доступа к файлу через /view/<storage_url>."""
    owner_id = get_owner_id(app)
    
    # Получаем storage_url первого документа
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ud.user_path, COALESCE(ud.original_filename, d.sha256)
                FROM user_documents ud
                JOIN documents d ON d.id = ud.document_id
                WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
                LIMIT 1;
            """, (owner_id,))
            row = cur.fetchone()
            assert row is not None, "Нет документов в БД для теста"
            storage_url, filename = row
    
    # Пробуем открыть файл через /view
    from urllib.parse import quote
    encoded_url = quote(storage_url, safe='')
    response = client.get(f'/view/{encoded_url}', headers={'X-User-ID': str(owner_id)})
    
    # Проверяем что файл доступен (200 или редирект на download)
    assert response.status_code in [200, 302], \
        f"Файл {storage_url} недоступен: status={response.status_code}"
    
    print(f"✅ Файл доступен через /view: {filename} → {storage_url}")


def test_09_search_in_db(client, app):
    """Проверка поиска по БД."""
    # Ищем распространённое слово (например, "договор" - есть во многих документах)
    owner_id = get_owner_id(app)
    response = client.post('/search', 
                          json={'search_terms': 'договор', 'exclude_mode': False},
                          headers={'X-User-ID': str(owner_id)})
    
    assert response.status_code == 200, f"Ошибка поиска: {response.data}"
    
    data = response.get_json()
    results = data.get('results', [])
    
    # Проверяем что есть результаты
    assert len(results) > 0, "Поиск не вернул результатов"
    
    # Проверяем структуру результата
    first_result = results[0]
    assert 'file' in first_result, "Результат не содержит поля 'file'"
    assert 'matches' in first_result, "Результат не содержит поля 'matches'"
    
    print(f"✅ Поиск работает: найдено {len(results)} документов с совпадениями")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
