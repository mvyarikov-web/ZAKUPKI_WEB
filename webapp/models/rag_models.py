"""Модели данных для RAG-системы.

Использует PostgreSQL с расширением pgvector для хранения векторных эмбеддингов.
"""
import psycopg2
from psycopg2.extras import execute_values
from typing import List, Dict, Any, Optional, Tuple
import json
from datetime import datetime


class DatabaseConnection:
    """Управление подключением к PostgreSQL."""
    
    def __init__(self, database_url: str):
        """
        Инициализация подключения.
        
        Args:
            database_url: URL подключения к PostgreSQL
        """
        self.database_url = database_url
        self._connection = None
    
    def connect(self) -> psycopg2.extensions.connection:
        """Создать подключение к БД."""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(self.database_url)
        return self._connection
    
    def close(self):
        """Закрыть подключение."""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    def __enter__(self):
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._connection:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
            self.close()


class RAGDatabase:
    """Класс для работы с RAG-базой данных."""
    
    def __init__(self, database_url: str):
        """
        Инициализация.
        
        Args:
            database_url: URL подключения к PostgreSQL
        """
        self.database_url = database_url
        self.db = DatabaseConnection(database_url)
    
    def initialize_schema(self):
        """Создать таблицы и расширения для RAG."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                # Устанавливаем расширение pgvector
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Таблица документов
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id SERIAL PRIMARY KEY,
                        file_path TEXT NOT NULL UNIQUE,
                        file_name TEXT NOT NULL,
                        file_hash TEXT,
                        file_size BIGINT,
                        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    );
                """)
                
                # Таблица чанков с векторами
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id SERIAL PRIMARY KEY,
                        document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        chunk_index INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        content_hash TEXT,
                        embedding vector(1536),
                        token_count INTEGER,
                        page_range TEXT,
                        section TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(document_id, chunk_index)
                    );
                """)
                
                # Индексы для быстрого поиска
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_document_id 
                    ON chunks(document_id);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                    ON chunks USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_documents_file_path 
                    ON documents(file_path);
                """)
                
                conn.commit()
    
    def add_document(
        self,
        file_path: str,
        file_name: str,
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Добавить документ в базу.
        
        Args:
            file_path: Путь к файлу
            file_name: Имя файла
            file_hash: Хеш файла
            file_size: Размер файла
            metadata: Дополнительные метаданные
            
        Returns:
            ID документа
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO documents (file_path, file_name, file_hash, file_size, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (file_path) DO UPDATE
                    SET file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_size = EXCLUDED.file_size,
                        metadata = EXCLUDED.metadata,
                        indexed_at = CURRENT_TIMESTAMP
                    RETURNING id;
                """, (file_path, file_name, file_hash, file_size, json.dumps(metadata) if metadata else None))
                
                doc_id = cur.fetchone()[0]
                conn.commit()
                return doc_id
    
    def add_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Добавить чанки в базу (батчем).
        
        Args:
            chunks: Список словарей с данными чанков:
                - document_id: ID документа
                - chunk_index: Индекс чанка
                - content: Текст чанка
                - content_hash: Хеш содержимого
                - embedding: Векторное представление (список float)
                - token_count: Количество токенов
                - page_range: Диапазон страниц
                - section: Раздел документа
                - metadata: Дополнительные метаданные
        """
        if not chunks:
            return
        
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                # Удаляем старые чанки для этого документа
                doc_ids = set(c['document_id'] for c in chunks)
                if doc_ids:
                    cur.execute(
                        "DELETE FROM chunks WHERE document_id = ANY(%s);",
                        (list(doc_ids),)
                    )
                
                # Вставляем новые чанки
                values = [
                    (
                        c['document_id'],
                        c['chunk_index'],
                        c['content'],
                        c.get('content_hash'),
                        c['embedding'],
                        c.get('token_count'),
                        c.get('page_range'),
                        c.get('section'),
                        json.dumps(c.get('metadata')) if c.get('metadata') else None
                    )
                    for c in chunks
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO chunks 
                    (document_id, chunk_index, content, content_hash, embedding, 
                     token_count, page_range, section, metadata)
                    VALUES %s
                    ON CONFLICT (document_id, chunk_index) DO UPDATE
                    SET content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        embedding = EXCLUDED.embedding,
                        token_count = EXCLUDED.token_count,
                        page_range = EXCLUDED.page_range,
                        section = EXCLUDED.section,
                        metadata = EXCLUDED.metadata;
                    """,
                    values
                )
                
                conn.commit()
    
    def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.7,
        document_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Найти похожие чанки по векторному сходству.
        
        Args:
            query_embedding: Вектор запроса
            top_k: Количество результатов
            min_similarity: Минимальный порог сходства (0-1)
            document_ids: Фильтр по документам (опционально)
            
        Returns:
            Список словарей с информацией о чанках и их релевантности
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT 
                        c.id,
                        c.document_id,
                        c.chunk_index,
                        c.content,
                        c.token_count,
                        c.page_range,
                        c.section,
                        c.metadata,
                        d.file_path,
                        d.file_name,
                        1 - (c.embedding <=> %s::vector) AS similarity
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE 1 - (c.embedding <=> %s::vector) >= %s
                """
                
                params = [query_embedding, query_embedding, min_similarity]
                
                if document_ids:
                    query += " AND c.document_id = ANY(%s)"
                    params.append(document_ids)
                
                query += " ORDER BY c.embedding <=> %s::vector LIMIT %s;"
                params.extend([query_embedding, top_k])
                
                cur.execute(query, params)
                
                results = []
                for row in cur.fetchall():
                    results.append({
                        'chunk_id': row[0],
                        'document_id': row[1],
                        'chunk_index': row[2],
                        'content': row[3],
                        'token_count': row[4],
                        'page_range': row[5],
                        'section': row[6],
                        'metadata': row[7],
                        'file_path': row[8],
                        'file_name': row[9],
                        'similarity': float(row[10])
                    })
                
                return results
    
    def get_document_by_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Получить документ по пути."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, file_path, file_name, file_hash, file_size, 
                           indexed_at, metadata
                    FROM documents
                    WHERE file_path = %s;
                """, (file_path,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'file_path': row[1],
                        'file_name': row[2],
                        'file_hash': row[3],
                        'file_size': row[4],
                        'indexed_at': row[5],
                        'metadata': row[6]
                    }
                return None
    
    def delete_document(self, file_path: str) -> bool:
        """Удалить документ и его чанки."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM documents WHERE file_path = %s;", (file_path,))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
    
    def get_stats(self) -> Dict[str, int]:
        """Получить статистику по базе."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM documents;")
                doc_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM chunks;")
                chunk_count = cur.fetchone()[0]
                
                return {
                    'documents': doc_count,
                    'chunks': chunk_count
                }
