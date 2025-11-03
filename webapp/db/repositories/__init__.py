"""
Репозитории для работы с БД (Data Access Layer).
"""
from .base_repository import BaseRepository
from .user_repository import UserRepository
from .document_repository import DocumentRepository
from .chunk_repository import ChunkRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "DocumentRepository",
    "ChunkRepository",
]
