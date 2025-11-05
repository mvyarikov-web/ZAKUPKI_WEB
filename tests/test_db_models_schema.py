"""
Тесты структуры моделей БД (инкремент 13, шаг 5).
Проверяем декларацию моделей на уровне SQLAlchemy (без реальных таблиц в БД):
- Импорт всех моделей
- Наличие всех таблиц в Base.metadata
- Корректность полей и связей в метаданных
- Relationships между моделями
"""

from datetime import datetime

from webapp.db import (
    Base,
    User, Session, Document, Chunk,
    AIConversation, AIMessage,
    SearchHistory, APIKey, UserModel,
    AppLog, JobQueue
)


# ==============================================================================
# Тесты импортов
# ==============================================================================

def test_all_models_importable():
    """Все модели импортируются без ошибок."""
    assert User is not None
    assert Session is not None
    assert Document is not None
    assert Chunk is not None
    assert AIConversation is not None
    assert AIMessage is not None
    assert SearchHistory is not None
    assert APIKey is not None
    assert UserModel is not None
    assert AppLog is not None
    assert JobQueue is not None


def test_base_metadata_has_tables():
    """Base.metadata содержит все таблицы."""
    table_names = Base.metadata.tables.keys()
    expected = {
        'users', 'sessions', 'documents', 'chunks',
        'ai_conversations', 'ai_messages',
        'search_history', 'api_keys', 'user_models',
        'app_logs', 'job_queue'
    }
    assert set(table_names) == expected


# ==============================================================================
# Тесты структуры таблиц через метаданные
# ==============================================================================

def test_users_table_in_metadata():
    """Таблица users присутствует в метаданных с необходимыми колонками."""
    table = Base.metadata.tables['users']
    columns = set(table.c.keys())
    
    assert 'id' in columns
    assert 'email' in columns
    assert 'password_hash' in columns
    assert 'role' in columns
    assert 'created_at' in columns
    assert 'updated_at' in columns


def test_sessions_table_in_metadata():
    """Таблица sessions присутствует в метаданных с FK."""
    table = Base.metadata.tables['sessions']
    columns = set(table.c.keys())
    
    assert 'user_id' in columns
    assert 'token_hash' in columns
    assert 'expires_at' in columns
    assert 'ip_address' in columns
    assert 'user_agent' in columns
    
    # Проверяем FK
    fks = list(table.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == 'users'


def test_documents_table_in_metadata():
    """Таблица documents имеет необходимые поля."""
    table = Base.metadata.tables['documents']
    columns = set(table.c.keys())
    
    assert 'id' in columns
    assert 'owner_id' in columns
    assert 'original_filename' in columns
    assert 'content_type' in columns
    assert 'size_bytes' in columns
    assert 'sha256' in columns
    assert 'blob' in columns
    assert 'storage_url' in columns
    assert 'status' in columns
    assert 'uploaded_at' in columns


def test_chunks_table_has_vector_column():
    """Таблица chunks имеет колонку embedding."""
    table = Base.metadata.tables['chunks']
    columns = set(table.c.keys())
    
    assert 'embedding' in columns
    assert 'document_id' in columns
    assert 'owner_id' in columns
    assert 'chunk_idx' in columns
    assert 'text' in columns


def test_ai_conversations_table():
    """Таблица ai_conversations присутствует."""
    assert 'ai_conversations' in Base.metadata.tables
    table = Base.metadata.tables['ai_conversations']
    columns = set(table.c.keys())
    assert 'user_id' in columns
    assert 'title' in columns


def test_search_history_table():
    """Таблица search_history существует."""
    table = Base.metadata.tables['search_history']
    columns = set(table.c.keys())
    assert 'user_id' in columns
    assert 'query_text' in columns
    assert 'filters' in columns
    assert 'results_count' in columns


def test_api_keys_table_structure():
    """Таблица api_keys имеет зашифрованные ключи."""
    table = Base.metadata.tables['api_keys']
    columns = set(table.c.keys())
    assert 'user_id' in columns
    assert 'provider' in columns
    assert 'key_ciphertext' in columns
    assert 'is_shared' in columns


def test_job_queue_table_structure():
    """Таблица job_queue имеет необходимые поля для очереди."""
    table = Base.metadata.tables['job_queue']
    columns = set(table.c.keys())
    assert 'type' in columns
    assert 'status' in columns
    assert 'priority' in columns
    assert 'payload' in columns
    assert 'locked_by' in columns
    assert 'locked_at' in columns


# ==============================================================================
# Тесты отношений (relationships) через SQLAlchemy Mapper
# ==============================================================================

def test_user_relationships():
    """User имеет правильные relationships."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(User)
    rels = {rel.key: rel for rel in mapper.relationships}
    
    assert 'sessions' in rels
    assert 'documents' in rels
    assert 'chunks' in rels
    assert 'conversations' in rels
    assert 'search_history' in rels
    assert 'api_keys' in rels
    assert 'user_models' in rels


def test_document_relationships():
    """Document имеет связь с chunks."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(Document)
    rels = {rel.key: rel for rel in mapper.relationships}
    
    assert 'owner' in rels
    assert 'chunks' in rels


def test_conversation_relationships():
    """AIConversation имеет связь с messages."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(AIConversation)
    rels = {rel.key: rel for rel in mapper.relationships}
    
    assert 'user' in rels
    assert 'messages' in rels


# ==============================================================================
# Тесты создания объектов
# ==============================================================================

def test_create_user_instance():
    """Можно создать экземпляр User."""
    user = User(
        email='test@example.com',
        password_hash='hashed_password',
        role='user'
    )
    assert user.email == 'test@example.com'
    assert user.role == 'user'
    assert user.created_at is None  # До сохранения в БД


def test_create_session_instance():
    """Можно создать экземпляр Session."""
    session = Session(
        user_id=1,
        token_hash='token_hash_123',
        expires_at=datetime.utcnow()
    )
    assert session.user_id == 1
    assert session.token_hash == 'token_hash_123'


def test_create_document_instance():
    """Можно создать экземпляр Document."""
    doc = Document(
        owner_id=1,
        original_filename='test.pdf',
        content_type='application/pdf',
        size_bytes=1024,
        sha256='abc123',
        status='new'
    )
    assert doc.original_filename == 'test.pdf'
    assert doc.status == 'new'


def test_create_chunk_instance():
    """Можно создать экземпляр Chunk."""
    chunk = Chunk(
        document_id=1,
        owner_id=1,
        chunk_idx=0,
        text='Sample text'
    )
    assert chunk.chunk_idx == 0
    assert chunk.text == 'Sample text'


def test_create_api_key_instance():
    """Можно создать экземпляр APIKey."""
    api_key = APIKey(
        user_id=1,
        provider='openai',
        key_ciphertext='encrypted_key',
        is_shared=False
    )
    assert api_key.provider == 'openai'
    assert api_key.is_shared is False


def test_create_job_instance():
    """Можно создать экземпляр JobQueue."""
    job = JobQueue(
        type='index',
        user_id=1,
        payload={'filename': 'test.txt'},
        status='queued',
        priority=0
    )
    assert job.type == 'index'
    assert job.status == 'queued'
    assert job.priority == 0


# ==============================================================================
# Тесты __repr__
# ==============================================================================

def test_user_repr():
    """User.__repr__ работает корректно."""
    user = User(id=1, email='test@example.com', role='admin')
    repr_str = repr(user)
    assert 'User' in repr_str
    assert 'test@example.com' in repr_str
    assert 'admin' in repr_str


def test_document_repr():
    """Document.__repr__ работает корректно."""
    doc = Document(id=1, original_filename='doc.pdf', status='indexed')
    repr_str = repr(doc)
    assert 'Document' in repr_str
    assert 'doc.pdf' in repr_str
    assert 'indexed' in repr_str
