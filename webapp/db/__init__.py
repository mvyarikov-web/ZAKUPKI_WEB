"""Пакет для работы с БД через SQLAlchemy."""

from .base import Base, engine, SessionLocal, get_db, get_db_context, init_db, drop_db
from .models import (
    User, Session, Document, Chunk,
    AIConversation, AIMessage,
    SearchHistory, APIKey, UserModel,
    AppLog, JobQueue, TokenUsage
)

__all__ = [
    'Base',
    'engine',
    'SessionLocal',
    'get_db',
    'get_db_context',
    'init_db',
    'drop_db',
    # Модели
    'User',
    'Session',
    'Document',
    'Chunk',
    'AIConversation',
    'AIMessage',
    'SearchHistory',
    'APIKey',
    'UserModel',
    'AppLog',
    'JobQueue',
    'TokenUsage',
]
