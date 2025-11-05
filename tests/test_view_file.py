"""
Тест для проверки просмотра файлов через /view/<path>.

Проверяет:
- Авторизацию через токен в URL
- Получение документа из БД
- Получение чанков из БД
- Сборку текста для отображения
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from webapp.db.base import Base
from webapp import create_app


def test_view_file_without_auth(client):
    """Тест просмотра файла без авторизации - должен вернуть 401."""
    response = client.get('/view/test_file.txt')
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'аутентификация' in data['error'].lower()


@pytest.fixture(scope='function', autouse=True)
def setup_test_database():
    """
    Изолированная БД для каждого теста этого файла.
    Подменяем глобальный SessionLocal на in-memory SQLite с общей связью для потоков.
    """
    test_engine = create_engine(
        'sqlite:///:memory:',
        echo=False,
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    import webapp.db.base
    original_session_local = webapp.db.base.SessionLocal
    webapp.db.base.SessionLocal = TestSessionLocal
    # Также переназначаем в модулях, которые импортировали SessionLocal напрямую
    try:
        import webapp.routes.auth as auth_routes
        auth_routes.SessionLocal = TestSessionLocal
    except Exception:
        pass
    try:
        import webapp.middleware.auth_middleware as auth_mw
        auth_mw.SessionLocal = TestSessionLocal
    except Exception:
        pass
    try:
        yield test_engine
    finally:
        webapp.db.base.SessionLocal = original_session_local
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture(scope='function')
def app(setup_test_database):
    """Создаёт Flask приложение, уже привязанное к тестовой БД."""
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_view_file_with_invalid_token(client):
    """Тест просмотра файла с невалидным токеном - должен вернуть 401."""
    response = client.get('/view/test_file.txt?token=invalid_token')
    
    assert response.status_code == 401


def test_view_file_not_found(client):
    """Тест просмотра несуществующего файла - должен вернуть 404 при валидной аутентификации."""
    # Регистрируем и логиним тестового пользователя, получаем валидный токен
    email = 'view_not_found@example.com'
    password = 'secret123'
    reg = client.post('/auth/register', json={'email': email, 'password': password})
    assert reg.status_code in (200, 201)
    token = reg.get_json().get('token')
    assert token

    # Делаем запрос с валидным токеном
    response = client.get(f'/view/nonexistent_file.txt?token={token}')
    assert response.status_code == 404
    data = response.get_json()
    assert 'индекс не создан' in data['error'].lower() or 'не найден' in data['error'].lower()


def test_view_file_success(client, sample_indexed_document):
    """Тест успешного просмотра проиндексированного файла."""
    # sample_indexed_document - фикстура, которая создаёт документ с чанками в БД
    doc, chunks = sample_indexed_document
    
    # Регистрируем и логиним пользователя, чтобы middleware допустил просмотр
    email = 'view_success@example.com'
    password = 'secret123'
    reg = client.post('/auth/register', json={'email': email, 'password': password})
    reg_json = reg.get_json()
    token = reg_json.get('token')
    user_id = reg_json.get('user', {}).get('id')
    # Присваиваем документ пользователю
    from webapp.db.base import get_db_context
    with get_db_context() as session:
        from webapp.db.repositories.document_repository import DocumentRepository
        repo = DocumentRepository(session)
        repo.update(doc.id, owner_id=user_id)
    
    # Запрашиваем просмотр файла
    response = client.get(f'/view/{doc.storage_url}?token={token}')
    
    assert response.status_code == 200
    assert response.content_type == 'text/html; charset=utf-8'
    
    # Проверяем, что в ответе есть текст из чанков
    html_content = response.data.decode('utf-8')
    for chunk in chunks:
        assert chunk.text in html_content


def test_view_file_with_keywords(client, sample_indexed_document):
    """Тест просмотра файла с подсветкой ключевых слов."""
    doc, chunks = sample_indexed_document
    # Авторизация
    email = 'view_keywords@example.com'
    password = 'secret123'
    reg = client.post('/auth/register', json={'email': email, 'password': password})
    reg_json = reg.get_json()
    token = reg_json.get('token')
    user_id = reg_json.get('user', {}).get('id')
    from webapp.db.base import get_db_context
    with get_db_context() as session:
        from webapp.db.repositories.document_repository import DocumentRepository
        DocumentRepository(session).update(doc.id, owner_id=user_id)
    
    # Используем ключевое слово, которое есть в тексте
    keyword = chunks[0].text.split()[0]  # Берём первое слово из первого чанка
    
    response = client.get(f'/view/{doc.storage_url}?token={token}&q={keyword}')
    
    assert response.status_code == 200
    html_content = response.data.decode('utf-8')
    
    # Проверяем, что ключевое слово подсвечено тегом <mark>
    assert f'<mark>{keyword}</mark>' in html_content or '<mark>' in html_content


def test_view_file_unsafe_path(client):
    """Тест защиты от path traversal атак."""
    email = 'view_unsafe@example.com'
    password = 'secret123'
    reg = client.post('/auth/register', json={'email': email, 'password': password})
    token = reg.get_json().get('token')
    
    # Пытаемся получить доступ к файлу вне uploads/
    response = client.get(f'/view/../../../etc/passwd?token={token}')
    
    assert response.status_code == 400
    data = response.get_json()
    assert 'недопустимый путь' in data['error'].lower()


def test_view_file_not_indexed_status(client, sample_document_not_indexed):
    """Тест просмотра файла, который загружен, но не проиндексирован."""
    doc = sample_document_not_indexed
    email = 'view_not_indexed@example.com'
    password = 'secret123'
    reg = client.post('/auth/register', json={'email': email, 'password': password})
    reg_json = reg.get_json()
    token = reg_json.get('token')
    user_id = reg_json.get('user', {}).get('id')
    from webapp.db.base import get_db_context
    with get_db_context() as session:
        from webapp.db.repositories.document_repository import DocumentRepository
        DocumentRepository(session).update(sample_document_not_indexed.id, owner_id=user_id)
    
    response = client.get(f'/view/{doc.storage_url}?token={token}')
    
    # Должен вернуть HTML с сообщением, что документ не проиндексирован
    assert response.status_code == 200
    html_content = response.data.decode('utf-8')
    assert 'не проиндексирован' in html_content.lower() or 'error-message' in html_content


# Фикстуры

@pytest.fixture
def test_user():
    """Тестовый пользователь."""
    return {
        'id': 1,
        'email': 'test@example.com',
        'role': 'user'
    }


@pytest.fixture
def auth_headers():
    """JWT токен для авторизации."""
    # Простой mock токен для тестов
    return {
        'Authorization': 'Bearer test_token_12345'
    }


@pytest.fixture
def sample_indexed_document(test_user):
    """
    Создаёт тестовый документ с чанками в БД.
    
    Returns:
        tuple: (document, chunks)
    """
    from webapp.db.base import get_db_context
    from webapp.db.repositories.document_repository import DocumentRepository
    from webapp.db.repositories.chunk_repository import ChunkRepository
    from webapp.db.models import DocumentStatus
    
    with get_db_context() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        # Убедимся, что пользователь с таким ID существует (FK на owner_id)
        from webapp.db.repositories.user_repository import UserRepository
        from webapp.db.models import UserRole
        user_repo = UserRepository(session)
        if not user_repo.find_one(id=test_user['id']):
            # Создадим минимального пользователя
            user = user_repo.create_user(email='sample_user@example.com', password_hash='noop', role=UserRole.USER)
            user.id = test_user['id']
            session.add(user)
            session.commit()
        
        # Создаём документ
        doc = doc_repo.create(
            owner_id=test_user['id'],
            storage_url='test_documents/sample.txt',
            original_filename='sample.txt',
            size_bytes=1024,
            sha256='test_hash_123',
            status=DocumentStatus.INDEXED.value
        )
        session.flush()
        
        # Создаём чанки
        chunks = []
        for i in range(3):
            chunk = chunk_repo.create_chunk(
                document_id=doc.id,
                owner_id=test_user['id'],
                text=f'Это тестовый текст чанка номер {i}. Содержит информацию для проверки.',
                chunk_idx=i,
                tokens=20
            )
            chunks.append(chunk)
        
        session.commit()
        
        yield doc, chunks
        
        # Cleanup
        doc_repo.delete(doc.id)


@pytest.fixture
def sample_document_not_indexed(test_user):
    """Создаёт документ без чанков (не проиндексирован)."""
    from webapp.db.base import get_db_context
    from webapp.db.repositories.document_repository import DocumentRepository
    from webapp.db.models import DocumentStatus
    
    with get_db_context() as session:
        doc_repo = DocumentRepository(session)
        # Убедимся, что есть пользователь
        from webapp.db.repositories.user_repository import UserRepository
        from webapp.db.models import UserRole
        user_repo = UserRepository(session)
        if not user_repo.find_one(id=test_user['id']):
            user = user_repo.create_user(email='not_indexed_user@example.com', password_hash='noop', role=UserRole.USER)
            user.id = test_user['id']
            session.add(user)
            session.commit()

        doc = doc_repo.create(
            owner_id=test_user['id'],
            storage_url='test_documents/not_indexed.txt',
            original_filename='not_indexed.txt',
            size_bytes=512,
            sha256='test_hash_456',
            status=DocumentStatus.PENDING.value
        )
        session.commit()
        
        yield doc
        
        # Cleanup
        doc_repo.delete(doc.id)
