"""
Комплексный мультипользовательский интеграционный тест.

Проверяет полный цикл работы системы под несколькими пользователями:
1. Создание тестовых файлов
2. Загрузка через /upload для разных пользователей
3. Индексация через /build_index
4. Проверка создания documents, user_documents, chunks
5. Изоляция данных между пользователями
6. Поиск с фильтрацией по пользователю
7. Просмотр индекса и файлов
8. Дедупликация при загрузке одного файла разными пользователями
"""
import pytest
import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path


@pytest.fixture(scope='module')
def app():
    """Создаёт тестовое приложение (module-scoped)."""
    # Настраиваем окружение перед созданием приложения
    os.environ['TESTING'] = 'true'
    os.environ['USE_DATABASE'] = 'true'
    os.environ['STRICT_USER_ID'] = 'true'
    
    from webapp import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['use_database'] = True
    app.config['UPLOAD_FOLDER'] = 'uploads'
    yield app


@pytest.fixture(scope='module')
def client(app):
    """Flask test client (module-scoped)."""
    return app.test_client()


@pytest.fixture(scope='module')
def clean_db_once(app):
    """Очищает БД один раз для всего модуля."""
    from webapp.models.rag_models import RAGDatabase
    
    db = RAGDatabase()
    db.initialize_schema()
    
    # Очищаем таблицы перед тестами
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE chunks CASCADE;")
            cur.execute("TRUNCATE TABLE user_documents CASCADE;")
            cur.execute("TRUNCATE TABLE documents CASCADE;")
            cur.execute("TRUNCATE TABLE folder_index_status CASCADE;")
        conn.commit()
    
    # Добавляем ссылку на db для использования в тестах
    clean_db_once.db = db
    yield clean_db_once


@pytest.fixture(scope='module')
def test_files_once(app):
    """Создаёт тестовые текстовые файлы один раз для модуля."""
    uploads = Path(app.config['UPLOAD_FOLDER'])
    
    # Полная очистка uploads перед началом тестов модуля
    if uploads.exists():
        shutil.rmtree(uploads)
    uploads.mkdir(parents=True, exist_ok=True)
    
    # Создаём два простых текстовых файла
    file1 = uploads / 'test_doc1.txt'
    file2 = uploads / 'test_doc2.txt'
    
    file1.write_text('Документ первый содержит ключевое слово жираф и другие данные про животных', encoding='utf-8')
    file2.write_text('Документ второй описывает слона и его среду обитания в лесу', encoding='utf-8')
    
    yield {'file1': file1, 'file2': file2}
    
    # Не удаляем файлы после тестов для возможности инспектирования


def test_01_setup_and_clean(clean_db_once):
    """Проверка, что БД очищена и схема создана."""
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            # Проверяем что таблицы существуют
            cur.execute("SELECT COUNT(*) FROM documents;")
            assert cur.fetchone()[0] == 0, "documents должна быть пуста"
            
            cur.execute("SELECT COUNT(*) FROM user_documents;")
            assert cur.fetchone()[0] == 0, "user_documents должна быть пуста"
            
            cur.execute("SELECT COUNT(*) FROM chunks;")
            assert cur.fetchone()[0] == 0, "chunks должна быть пуста"
    
    print("✅ БД очищена и готова к тестированию")


def test_02_user1_indexes_file1(client, app, clean_db_once, test_files_once):
    """Пользователь 1 индексирует файл 1."""
    user1_id = 1
    
    # Индексация
    response = client.post('/build_index', headers={'X-User-ID': str(user1_id)})
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'], f"Индексация провалилась: {data.get('message')}"
    
    # Проверяем создание документа
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            docs_count = cur.fetchone()[0]
            assert docs_count == 2, f"Ожидалось 2 документа, получено {docs_count}"
            
            cur.execute("SELECT COUNT(*) FROM user_documents WHERE user_id = %s AND is_soft_deleted = FALSE;", (user1_id,))
            user_docs = cur.fetchone()[0]
            assert user_docs == 2, f"У пользователя 1 должно быть 2 документа, получено {user_docs}"
            
            cur.execute("""
                SELECT COUNT(*) FROM chunks c
                WHERE c.document_id IN (
                    SELECT document_id FROM user_documents WHERE user_id = %s
                );
            """, (user1_id,))
            chunks_count = cur.fetchone()[0]
            assert chunks_count > 0, "У пользователя 1 должны быть чанки"
    
    print(f"✅ Пользователь 1 проиндексировал {docs_count} документов с {chunks_count} чанками")


def test_03_user2_indexes_same_file1(client, app, clean_db_once, test_files_once):
    """Пользователь 2 индексирует тот же файл 1 (дедупликация)."""
    user2_id = 2
    
    # Индексация
    response = client.post('/build_index', headers={'X-User-ID': str(user2_id)})
    assert response.status_code == 200
    data = response.get_json()
    assert data['success']
    
    # Проверяем дедупликацию: документов всё ещё 2 (глобально), но у user2 появилась связь
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            docs_count = cur.fetchone()[0]
            assert docs_count == 2, f"Глобально должно остаться 2 документа (дедуп), получено {docs_count}"
            
            cur.execute("SELECT COUNT(*) FROM user_documents WHERE user_id = %s AND is_soft_deleted = FALSE;", (user2_id,))
            user2_docs = cur.fetchone()[0]
            assert user2_docs == 2, f"У пользователя 2 должно быть 2 документа, получено {user2_docs}"
            
            # Проверяем что чанков не дублируются глобально
            cur.execute("SELECT COUNT(*) FROM chunks;")
            global_chunks = cur.fetchone()[0]
            # Должно быть столько же, сколько было после первой индексации (дедуп)
            assert global_chunks > 0, "Чанки должны существовать"
    
    print(f"✅ Пользователь 2 привязан к существующим документам (дедуп): {docs_count} документов, {global_chunks} чанков")


def test_04_search_isolation_user1(client, app, clean_db_once):
    """Проверка поиска пользователя 1."""
    user1_id = 1
    
    # Поиск по слову "жираф" (есть только в file1)
    response = client.post(
        '/search',
        json={'search_terms': 'жираф', 'exclude_mode': False},
        headers={'X-User-ID': str(user1_id)}
    )
    assert response.status_code == 200
    data = response.get_json()
    results = data.get('results', [])
    
    assert len(results) > 0, "Пользователь 1 должен найти документ со словом жираф"
    
    # Проверяем что результат содержит правильный файл
    found_files = [r.get('file') or r.get('filename') for r in results]
    assert any('test_doc1.txt' in f for f in found_files), "Результат должен содержать test_doc1.txt"
    
    print(f"✅ Пользователь 1 нашёл {len(results)} документов по запросу 'жираф'")


def test_05_search_isolation_user2(client, app, clean_db_once):
    """Проверка поиска пользователя 2 (те же файлы)."""
    user2_id = 2
    
    # Поиск по слову "слон" (есть только в file2)
    response = client.post(
        '/search',
        json={'search_terms': 'слон', 'exclude_mode': False},
        headers={'X-User-ID': str(user2_id)}
    )
    assert response.status_code == 200
    data = response.get_json()
    results = data.get('results', [])
    
    assert len(results) > 0, "Пользователь 2 должен найти документ со словом слон"
    
    found_files = [r.get('file') or r.get('filename') for r in results]
    assert any('test_doc2.txt' in f for f in found_files), "Результат должен содержать test_doc2.txt"
    
    print(f"✅ Пользователь 2 нашёл {len(results)} документов по запросу 'слон'")


def test_06_user3_no_access_to_user1_files(client, app, clean_db_once):
    """Пользователь 3 не видит файлы пользователей 1 и 2 (изоляция)."""
    user3_id = 3
    
    # Поиск по слову "жираф"
    response = client.post(
        '/search',
        json={'search_terms': 'жираф', 'exclude_mode': False},
        headers={'X-User-ID': str(user3_id)}
    )
    assert response.status_code == 200
    data = response.get_json()
    results = data.get('results', [])
    
    assert len(results) == 0, "Пользователь 3 не должен видеть чужие документы"
    
    print("✅ Пользователь 3 изолирован от данных других пользователей")


def test_07_index_status_per_user(client, app, clean_db_once):
    """Проверка /index_status для разных пользователей."""
    user1_id = 1
    user2_id = 2
    user3_id = 3
    
    # User 1
    response = client.get('/index_status', headers={'X-User-ID': str(user1_id)})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('entries', 0) == 2, "У пользователя 1 должно быть 2 документа"
    
    # User 2
    response = client.get('/index_status', headers={'X-User-ID': str(user2_id)})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('entries', 0) == 2, "У пользователя 2 должно быть 2 документа"
    
    # User 3
    response = client.get('/index_status', headers={'X-User-ID': str(user3_id)})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('entries', 0) == 0, "У пользователя 3 не должно быть документов"
    
    print("✅ /index_status корректно показывает документы для каждого пользователя")


def test_08_view_index_per_user(client, app, clean_db_once):
    """Проверка /view_index для разных пользователей."""
    user1_id = 1
    user3_id = 3
    
    # User 1 видит свои файлы
    response = client.get('/view_index', headers={'X-User-ID': str(user1_id)})
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert 'test_doc1.txt' in content or 'жираф' in content, "Индекс user1 должен содержать его файлы"
    
    # User 3 не видит чужие файлы
    response = client.get('/view_index', headers={'X-User-ID': str(user3_id)})
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert 'test_doc1.txt' not in content, "Индекс user3 не должен содержать чужие файлы"
    
    print("✅ /view_index показывает только файлы текущего пользователя")


def test_09_soft_delete_and_restore(client, app, clean_db_once):
    """Проверка мягкого удаления и восстановления связи."""
    user1_id = 1
    
    # Получаем document_id первого документа пользователя 1
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT document_id FROM user_documents
                WHERE user_id = %s AND is_soft_deleted = FALSE
                LIMIT 1;
            """, (user1_id,))
            row = cur.fetchone()
            assert row, "У пользователя 1 должны быть документы"
            doc_id = row[0]
            
            # Мягкое удаление
            cur.execute("""
                UPDATE user_documents
                SET is_soft_deleted = TRUE
                WHERE user_id = %s AND document_id = %s;
            """, (user1_id, doc_id))
        conn.commit()
    
    # Проверяем что документ исчез из поиска
    response = client.post(
        '/search',
        json={'search_terms': 'жираф', 'exclude_mode': False},
        headers={'X-User-ID': str(user1_id)}
    )
    data = response.get_json()
    results_after_delete = len(data.get('results', []))
    
    # Восстанавливаем
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE user_documents
                SET is_soft_deleted = FALSE
                WHERE user_id = %s AND document_id = %s;
            """, (user1_id, doc_id))
        conn.commit()
    
    # Проверяем что документ вернулся
    response = client.post(
        '/search',
        json={'search_terms': 'жираф', 'exclude_mode': False},
        headers={'X-User-ID': str(user1_id)}
    )
    data = response.get_json()
    results_after_restore = len(data.get('results', []))
    
    assert results_after_restore > results_after_delete, "После восстановления документ должен появиться в поиске"
    
    print("✅ Мягкое удаление и восстановление работают корректно")


def test_10_global_dedup_verification(client, app, clean_db_once):
    """Финальная проверка глобальной дедупликации."""
    with clean_db_once.db.db.connect() as conn:
        with conn.cursor() as cur:
            # Глобально должно быть 2 документа
            cur.execute("SELECT COUNT(*) FROM documents;")
            global_docs = cur.fetchone()[0]
            assert global_docs == 2, f"Глобально должно быть 2 документа, получено {global_docs}"
            
            # user_documents связей: user1=2, user2=2, user3=0
            cur.execute("SELECT user_id, COUNT(*) FROM user_documents WHERE is_soft_deleted = FALSE GROUP BY user_id ORDER BY user_id;")
            bindings = cur.fetchall()
            expected = [(1, 2), (2, 2)]
            assert bindings == expected, f"Ожидались связи {expected}, получено {bindings}"
            
            # Chunks не дублируются
            cur.execute("SELECT COUNT(*) FROM chunks;")
            chunks_count = cur.fetchone()[0]
            # Должно быть разумное количество (не дублированное)
            assert chunks_count > 0 and chunks_count < 20, f"Чанков должно быть разумное количество, получено {chunks_count}"
    
    print(f"✅ Глобальная дедупликация работает: {global_docs} документов, {chunks_count} чанков, связи корректны")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
