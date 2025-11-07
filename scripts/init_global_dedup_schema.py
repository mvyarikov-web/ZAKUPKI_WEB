"""Инициализация схемы глобального дедупа документов (инкремент 017).

Создаёт три таблицы:
- documents (глобальный контент, один экземпляр по sha256)
- chunks (чанки одного документа)
- user_documents (связь пользователя с документом и видимость)

Повторный запуск безопасен: старые таблицы удаляются.
"""
import os
import psycopg2
from psycopg2 import sql
from pathlib import Path

ENV_FILE = ".env"

DDL_STATEMENTS = [
    # Расширение для векторов (опционально, если используется эмбеддинги)
    "CREATE EXTENSION IF NOT EXISTS vector;",
    # Удаление старых таблиц (если были прежние версии)
    "DROP TABLE IF EXISTS user_documents CASCADE;",
    "DROP TABLE IF EXISTS chunks CASCADE;",
    "DROP TABLE IF EXISTS documents CASCADE;",
    # documents: глобальный единичный экземпляр
    """
    CREATE TABLE documents (
        id SERIAL PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        size_bytes BIGINT,
        mime TEXT,
        extracted_at TIMESTAMPTZ,
        parse_status TEXT,
        storage_pointer TEXT,
        indexing_cost_seconds DOUBLE PRECISION DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # chunks: чанки одного документа
    """
    CREATE TABLE chunks (
        id SERIAL PRIMARY KEY,
        document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chunk_index INT NOT NULL,
        text TEXT NOT NULL,
        vector vector(1536),
        length INT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id, chunk_index)
    );
    """,
    # user_documents: связь пользователя с документом
    """
    CREATE TABLE user_documents (
        user_id INT NOT NULL,
        document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        original_filename TEXT,
        user_path TEXT,
        added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        is_soft_deleted BOOLEAN DEFAULT FALSE,
        tags JSONB,
        PRIMARY KEY(user_id, document_id)
    );
    """,
    # Индекс активных связей
    "CREATE INDEX user_documents_active_idx ON user_documents(user_id, document_id) WHERE is_soft_deleted = FALSE;",
    # Индекс для быстрого поиска чанков по документу
    "CREATE INDEX chunks_document_idx ON chunks(document_id);",
]


def load_env_dsn(env_path: str = ENV_FILE) -> str:
    """Загрузить DATABASE_URL из .env (или вернуть ошибку)."""
    if not os.path.exists(env_path):
        raise FileNotFoundError(f".env не найден: {env_path}")
    dsn = None
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.upper().startswith('DATABASE_URL='):
                dsn = line.split('=', 1)[1].strip()
                break
    if not dsn:
        raise RuntimeError("DATABASE_URL не найден в .env")
    # Приводим схему к psycopg2 (убираем +psycopg2 если есть)
    dsn = dsn.replace('postgresql+psycopg2://', 'postgresql://')
    return dsn


def init_schema(dsn: str) -> None:
    """Применить DDL для создания схемы."""
    print("Подключение к БД...")
    conn = psycopg2.connect(dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                for stmt in DDL_STATEMENTS:
                    print(f"DDL: {stmt.splitlines()[0][:60]}...")
                    cur.execute(sql.SQL(stmt))
        print("Схема создана успешно.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        dsn = load_env_dsn()
        init_schema(dsn)
    except Exception as e:
        print(f"Ошибка инициализации схемы: {e}")
        raise
