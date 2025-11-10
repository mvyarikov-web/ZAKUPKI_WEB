"""
Модели данных для SQLAlchemy (инкремент 13).
Все сущности из спецификации раздела 1.1 (Фаза 1).
"""

from datetime import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    ForeignKey, LargeBinary, Enum as SQLEnum, JSON, Index, UniqueConstraint, Float
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from webapp.db.base import Base


# ==============================================================================
# ENUM TYPES
# ==============================================================================

class UserRole(str, enum.Enum):
    """Роли пользователей."""
    USER = 'user'
    ADMIN = 'admin'


class DocumentStatus(str, enum.Enum):
    """Статусы обработки документов."""
    PENDING = 'new'  # Новый/ожидает обработки
    PROCESSING = 'parsed'  # Парсится
    INDEXED = 'indexed'  # Проиндексирован
    FAILED = 'error'  # Ошибка


class MessageRole(str, enum.Enum):
    """Роли сообщений в диалоге."""
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'


class LogLevel(str, enum.Enum):
    """Уровни логирования."""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


class JobType(str, enum.Enum):
    """Типы фоновых задач."""
    INDEX = 'index'
    OCR = 'ocr'
    EMBED = 'embed'
    CLEANUP = 'cleanup'


class JobStatus(str, enum.Enum):
    """Статусы выполнения задач."""
    QUEUED = 'queued'
    RUNNING = 'running'
    DONE = 'done'
    ERROR = 'error'


# ==============================================================================
# ПОЛЬЗОВАТЕЛИ И СЕССИИ
# ==============================================================================

class User(Base):
    """Пользователь системы."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum('user', 'admin', name='user_role'), default='user', nullable=False)
    first_name = Column(String(100), nullable=True)  # Имя пользователя
    last_name = Column(String(100), nullable=True)   # Фамилия пользователя
    last_folder = Column(String(500), nullable=True)  # Последняя открытая папка
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    # Легаси-архитектура: пользователи связаны с документами через user_documents
    conversations = relationship('AIConversation', back_populates='user')
    search_history = relationship('SearchHistory', back_populates='user')
    api_keys = relationship('APIKey', back_populates='user')
    user_models = relationship('UserModel', back_populates='user')
    prompts = relationship('Prompt', back_populates='user')
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"

class Session(Base):
    """JWT-токены и активные сессии."""
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    ip_address = Column(String(45))  # IPv6 поддержка
    user_agent = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    user = relationship('User', back_populates='sessions')
    
    __table_args__ = (
        Index('idx_sessions_user_expires', 'user_id', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


# ==============================================================================
# ДОКУМЕНТЫ И ЧАНКИ (ЛЕГАСИ-АРХИТЕКТУРА)
# ==============================================================================

class Document(Base):
    """
    Глобальное хранилище документов (легаси-архитектура).
    Документы независимы от пользователей, дедуплицируются по SHA256.
    Связь с пользователями через таблицу user_documents.
    
    С инкремента 020: добавлено поле blob для хранения файлов в БД.
    """
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sha256 = Column(String(64), nullable=False, unique=True)  # UNIQUE для глобальной дедупликации
    size_bytes = Column(Integer, nullable=False)
    mime = Column(String(127))  # тип файла
    parse_status = Column(Text)  # статус обработки: 'indexed', 'error', etc.
    blob = Column(LargeBinary, nullable=True)  # Бинарное содержимое файла (PURE_DB_MODE)
    
    # Поля для расчёта ценности документа при GC
    access_count = Column(Integer, default=0, nullable=False)  # счётчик обращений
    indexing_cost_seconds = Column(Float, default=0.0, nullable=False)  # время индексации
    last_accessed_at = Column(DateTime)  # последнее обращение
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    chunks = relationship('Chunk', back_populates='document', cascade='all, delete-orphan')
    user_links = relationship('UserDocument', back_populates='document', cascade='all, delete-orphan')
    
    __table_args__ = (
        UniqueConstraint('sha256', name='uq_documents_sha256'),
    )
    
    def __repr__(self):
        return f"<Document(id={self.id}, sha256='{self.sha256[:8]}...', size={self.size_bytes})>"


class UserDocument(Base):
    """
    Связь пользователей с документами (легаси-архитектура).
    Один документ может принадлежать многим пользователям.
    """
    __tablename__ = 'user_documents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    original_filename = Column(Text)  # имя файла у конкретного пользователя
    user_path = Column(Text)  # путь в папке пользователя
    is_soft_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    access_level = Column(String(50), default='read', nullable=False)
    
    # Связи
    user = relationship('User', backref='user_documents')
    document = relationship('Document', back_populates='user_links')
    
    __table_args__ = (
        UniqueConstraint('user_id', 'document_id', name='uq_user_document'),
        Index('ix_user_documents_user_id', 'user_id'),
        Index('ix_user_documents_document_id', 'document_id'),
    )
    
    def __repr__(self):
        return f"<UserDocument(user_id={self.user_id}, document_id={self.document_id}, filename='{self.original_filename}')>"
        return f"<UserDocument(user_id={self.user_id}, document_id={self.document_id}, filename='{self.original_filename}')>"


class Chunk(Base):
    """Чанки текста для RAG (легаси-архитектура, принадлежат глобальным документам)."""
    __tablename__ = 'chunks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    chunk_idx = Column(Integer, nullable=False)  # Порядковый номер чанка в документе
    text = Column(Text, nullable=False)
    text_sha256 = Column(String(64), index=True)
    tokens = Column(Integer)
    embedding = Column(Vector(1536))  # OpenAI ada-002 размерность
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    document = relationship('Document', back_populates='chunks')
    
    __table_args__ = (
        Index('idx_chunks_document', 'document_id', 'chunk_idx'),
        UniqueConstraint('document_id', 'chunk_idx', name='uq_chunks_doc_idx'),
        # IVFFlat индекс будет создан вручную в миграции
    )
    
    def __repr__(self):
        return f"<Chunk(id={self.id}, document_id={self.document_id}, chunk_idx={self.chunk_idx})>"

# ==============================================================================
# AI ДИАЛОГИ И СООБЩЕНИЯ
# ==============================================================================

class AIConversation(Base):
    """Диалоги с AI."""
    __tablename__ = 'ai_conversations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = relationship('User', back_populates='conversations')
    messages = relationship('AIMessage', back_populates='conversation', 
                          cascade='all, delete-orphan', order_by='AIMessage.created_at')
    
    __table_args__ = (
        Index('idx_conversations_user_updated', 'user_id', 'updated_at'),
    )
    
    def __repr__(self):
        return f"<AIConversation(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class AIMessage(Base):
    """Сообщения в диалогах с AI."""
    __tablename__ = 'ai_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey('ai_conversations.id', ondelete='CASCADE'), 
                            nullable=False)
    role = Column(SQLEnum('user', 'assistant', 'system', name='message_role'), nullable=False)
    content = Column(Text, nullable=False)
    tokens = Column(Integer)
    cost = Column(Integer)  # В копейках для точности
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    conversation = relationship('AIConversation', back_populates='messages')
    
    __table_args__ = (
        Index('idx_messages_conversation', 'conversation_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AIMessage(id={self.id}, conversation_id={self.conversation_id}, role='{self.role}')>"


# ==============================================================================
# ПОИСК
# ==============================================================================

class SearchHistory(Base):
    """История поисковых запросов."""
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    query_text = Column(Text, nullable=False)
    filters = Column(JSON)  # Дополнительные фильтры поиска
    results_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Связи
    user = relationship('User', back_populates='search_history')
    
    __table_args__ = (
        Index('idx_search_history_user_created', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SearchHistory(id={self.id}, user_id={self.user_id}, query='{self.query_text[:50]}')>"


# ==============================================================================
# API КЛЮЧИ И МОДЕЛИ
# ==============================================================================

class APIKey(Base):
    """API ключи провайдеров (зашифрованные)."""
    __tablename__ = 'api_keys'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    provider = Column(String(63), nullable=False)  # openai, anthropic, deepseek, etc.
    key_ciphertext = Column(Text, nullable=False)  # Fernet encrypted
    is_shared = Column(Boolean, default=False)  # Доступен всем пользователям (админский)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    user = relationship('User', back_populates='api_keys')
    
    __table_args__ = (
        Index('idx_api_keys_user_provider', 'user_id', 'provider'),
    )
    
    def __repr__(self):
        return f"<APIKey(id={self.id}, user_id={self.user_id}, provider='{self.provider}')>"


class Prompt(Base):
    """Промпты пользователей."""
    __tablename__ = 'prompts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)  # Название промпта
    content = Column(Text, nullable=False)  # Текст промпта
    is_shared = Column(Boolean, default=False)  # Доступен всем пользователям (админский)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = relationship('User', back_populates='prompts')
    
    __table_args__ = (
        Index('idx_prompts_user', 'user_id'),
    )
    
    def __repr__(self):
        return f"<Prompt(id={self.id}, user_id={self.user_id}, name='{self.name}')>"


class UserModel(Base):
    """Модели пользователя с настройками и ценами."""
    __tablename__ = 'user_models'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    model_id = Column(String(127), nullable=False)  # gpt-4, claude-3, etc.
    display_name = Column(String(255))
    pricing = Column(JSON)  # Структура с ценами за токены
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    user = relationship('User', back_populates='user_models')
    
    __table_args__ = (
        Index('idx_user_models_user_active', 'user_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<UserModel(id={self.id}, user_id={self.user_id}, model_id='{self.model_id}')>"


# ==============================================================================
# ЛОГИ И ОЧЕРЕДЬ ЗАДАЧ
# ==============================================================================

class AppLog(Base):
    """Системные логи приложения."""
    __tablename__ = 'app_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(SQLEnum('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', name='log_level'), 
                  nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    component = Column(String(127))  # Имя модуля/компонента
    message = Column(Text, nullable=False)
    context_json = Column(JSON)  # Дополнительный контекст
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_app_logs_level_created', 'level', 'created_at'),
        Index('idx_app_logs_user_created', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AppLog(id={self.id}, level='{self.level}', component='{self.component}')>"


class JobQueue(Base):
    """Очередь фоновых задач."""
    __tablename__ = 'job_queue'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(SQLEnum('index', 'ocr', 'embed', 'cleanup', name='job_type'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    payload = Column(JSON, nullable=False)  # Параметры задачи
    status = Column(SQLEnum('queued', 'running', 'done', 'error', name='job_status'), 
                   default='queued', nullable=False)
    priority = Column(Integer, default=0)
    locked_by = Column(String(63))  # ID воркера
    locked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_job_queue_status_priority', 'status', 'priority', 'created_at'),
        Index('idx_job_queue_user', 'user_id'),
    )
    
    def __repr__(self):
        return f"<JobQueue(id={self.id}, type='{self.type}', status='{self.status}')>"


class HTTPRequestLog(Base):
    """Логи HTTP запросов к API."""
    __tablename__ = 'http_request_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    method = Column(String(10), nullable=False)  # GET, POST, PUT, DELETE, etc.
    path = Column(String(500), nullable=False)  # URL path
    query_params = Column(JSON)  # Query parameters
    request_body = Column(Text)  # Request body (может быть большим)
    response_status = Column(Integer)  # HTTP status code
    response_time_ms = Column(Integer)  # Время обработки в миллисекундах
    ip_address = Column(String(45))  # IPv4 или IPv6
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_http_logs_user_created', 'user_id', 'created_at'),
        Index('idx_http_logs_path_created', 'path', 'created_at'),
        Index('idx_http_logs_status', 'response_status'),
    )
    
    def __repr__(self):
        return f"<HTTPRequestLog(id={self.id}, method='{self.method}', path='{self.path}', status={self.response_status})>"


class ErrorLog(Base):
    """Логи ошибок и исключений."""
    __tablename__ = 'error_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    error_type = Column(String(255), nullable=False)  # Тип исключения (ValueError, HTTPError, etc.)
    error_message = Column(Text, nullable=False)  # Сообщение об ошибке
    stack_trace = Column(Text)  # Полный traceback
    component = Column(String(127))  # Модуль/компонент где произошла ошибка
    request_path = Column(String(500))  # URL если ошибка в HTTP-обработчике
    request_data = Column(JSON)  # Данные запроса
    context_json = Column(JSON)  # Дополнительный контекст
    is_resolved = Column(Boolean, default=False)  # Флаг для отслеживания исправления
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_error_logs_type_created', 'error_type', 'created_at'),
        Index('idx_error_logs_component', 'component'),
        Index('idx_error_logs_unresolved', 'is_resolved', 'created_at'),
    )
    
    def __repr__(self):
        return f"<ErrorLog(id={self.id}, type='{self.error_type}', component='{self.component}', resolved={self.is_resolved})>"


# ==============================================================================
# ИСПОЛЬЗОВАНИЕ ТОКЕНОВ МОДЕЛЕЙ (СТАТИСТИКА)
# ==============================================================================

class TokenUsage(Base):
    """Статистика использования токенов по моделям (замена файлового token_usage.json)."""
    __tablename__ = 'token_usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    model_id = Column(String(127), nullable=False, index=True)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Integer)  # округляем до int для простоты агрегаций
    cost_usd = Column(Integer)  # храним в центах для точности; на уровне сервиса преобразуем
    cost_rub = Column(Integer)  # храним в копейках
    input_cost_usd = Column(Integer)  # центы
    output_cost_usd = Column(Integer)  # центы
    metadata_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index('idx_token_usage_model_created', 'model_id', 'created_at'),
        Index('idx_token_usage_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<TokenUsage(id={self.id}, model_id='{self.model_id}', total_tokens={self.total_tokens})>"


class AIModelConfig(Base):
    """Конфигурация AI моделей (замена models.json)."""
    __tablename__ = 'ai_model_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(127), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)
    provider = Column(String(63), nullable=False)  # openai, perplexity, deepseek, etc.
    context_window_tokens = Column(Integer, nullable=False, default=4096)
    max_output_tokens = Column(Integer)
    price_input_per_1m = Column(Integer, default=0)  # центы
    price_output_per_1m = Column(Integer, default=0)  # центы
    price_per_1000_requests = Column(Integer)  # центы, для моделей с посчётом за запросы
    pricing_model = Column(String(31), default='per_token')  # per_token или per_request
    supports_system_role = Column(Boolean, default=True)
    supports_streaming = Column(Boolean, default=True)
    supports_function_calling = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    timeout_seconds = Column(Integer, default=60)
    config_json = Column(JSON)  # дополнительные настройки
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ai_model_configs_provider_enabled', 'provider', 'is_enabled'),
        Index('idx_ai_model_configs_default', 'is_default'),
    )
    
    def __repr__(self):
        return f"<AIModelConfig(id={self.id}, model_id='{self.model_id}', provider='{self.provider}')>"


class FileSearchState(Base):
    """Состояния файлов при поиске (замена search_results.json)."""
    __tablename__ = 'file_search_state'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    file_path = Column(String(1000), nullable=False)  # относительный путь от uploads/
    status = Column(String(63), nullable=False)  # not_checked, processing, contains_keywords, no_keywords, error
    search_terms = Column(Text)  # последние поисковые термины
    result_json = Column(JSON)  # детали результата
    last_checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_file_search_state_user_file', 'user_id', 'file_path', unique=True),
        Index('idx_file_search_state_status', 'status'),
        Index('idx_file_search_state_updated', 'updated_at'),
    )
    
    def __repr__(self):
        return f"<FileSearchState(id={self.id}, user_id={self.user_id}, file_path='{self.file_path}', status='{self.status}')>"


class SearchIndex(Base):
    """Поисковый индекс документов (замена _search_index.txt)."""
    __tablename__ = 'search_index'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text, nullable=False)  # Текстовое содержимое документа
    metadata_json = Column('metadata', JSON, nullable=True)  # Метаданные (имя файла, путь, размер и т.д.)
    search_vector = Column(Text, nullable=True)  # tsvector для полнотекстового поиска (управляется триггером)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship('Document', foreign_keys=[document_id])
    user = relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_search_index_document', 'document_id'),
        Index('idx_search_index_user', 'user_id'),
        Index('idx_search_index_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SearchIndex(id={self.id}, document_id={self.document_id}, user_id={self.user_id})>"


# ==============================================================================
# СТАТУС ИНДЕКСАЦИИ ПАПОК
# ==============================================================================

class FolderIndexStatus(Base):
    """Статус индексации папок пользователей."""
    __tablename__ = 'folder_index_status'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    folder_path = Column(Text, nullable=False)
    root_hash = Column(Text)
    last_indexed_at = Column(DateTime)
    status_data = Column(JSON, nullable=True)  # JSONB данные прогресса индексации (инкремент 020)
    
    # Связи
    owner = relationship('User', backref='folder_statuses')
    
    __table_args__ = (
        UniqueConstraint('owner_id', 'folder_path', name='uq_folder_status'),
        Index('ix_folder_index_status_owner', 'owner_id'),
    )
    
    def __repr__(self):
        return f"<FolderIndexStatus(id={self.id}, owner_id={self.owner_id}, folder_path='{self.folder_path}')>"


class AppSettings(Base):
    """Глобальные настройки приложения (инкремент 020)."""
    __tablename__ = 'app_settings'
    
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<AppSettings(key='{self.key}', value='{self.value[:50]}...')>"


# Экспорт всех моделей
__all__ = [
    'User',
    'Session',
    'Document',
    'Chunk',
    'AIConversation',
    'UserDocument',
    'AIMessage',
    'SearchHistory',
    'APIKey',
    'UserModel',
    'Prompt',
    'AppLog',
    'JobQueue',
    'HTTPRequestLog',
    'ErrorLog',
    'TokenUsage',
    'AIModelConfig',
    'FileSearchState',
    'SearchIndex',
    'FolderIndexStatus',
    'AppSettings',
]
