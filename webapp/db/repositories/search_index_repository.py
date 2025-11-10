"""
Репозиторий для работы с поисковым индексом (таблица search_index).

Заменяет файловый индекс _search_index.txt.
Использует PostgreSQL full-text search с tsvector.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2 import sql

logger = logging.getLogger(__name__)


class SearchIndexRepository:
    """Репозиторий для работы с таблицей search_index."""
    
    def __init__(self, db_connection):
        """
        Args:
            db_connection: Подключение к БД (psycopg2 connection)
        """
        self.db = db_connection
    
    def create_or_update_index(
        self,
        document_id: int,
        user_id: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Создаёт или обновляет запись в поисковом индексе.
        
        Args:
            document_id: ID документа
            user_id: ID пользователя
            content: Текстовое содержимое для индексации
            metadata: Метаданные (имя файла, путь, размер и т.д.)
            
        Returns:
            ID созданной/обновлённой записи
        """
        import json
        
        with self.db.cursor() as cur:
            # Проверяем, существует ли запись
            cur.execute(
                """
                SELECT id FROM search_index
                WHERE document_id = %s AND user_id = %s;
                """,
                (document_id, user_id)
            )
            existing = cur.fetchone()
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            if existing:
                # Обновляем существующую запись
                cur.execute(
                    """
                    UPDATE search_index
                    SET content = %s, metadata = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id;
                    """,
                    (content, metadata_json, existing[0])
                )
                logger.info(f"Обновлён поисковый индекс для документа {document_id}")
                return existing[0]
            else:
                # Создаём новую запись
                cur.execute(
                    """
                    INSERT INTO search_index (document_id, user_id, content, metadata, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id;
                    """,
                    (document_id, user_id, content, metadata_json)
                )
                new_id = cur.fetchone()[0]
                logger.info(f"Создан поисковый индекс для документа {document_id}, id={new_id}")
                return new_id
    
    def search(
        self,
        user_id: int,
        keywords: List[str],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Поиск по ключевым словам с использованием full-text search.
        
        Args:
            user_id: ID пользователя
            keywords: Список ключевых слов для поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список словарей с результатами поиска
        """
        if not keywords:
            return []
        
        # Формируем поисковый запрос для tsquery
        search_query = ' | '.join(keywords)  # OR между словами
        
        results = []
        
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    si.id,
                    si.document_id,
                    si.content,
                    si.metadata,
                    ts_rank(si.search_vector, to_tsquery('russian', %s)) as rank,
                    ts_headline('russian', si.content, to_tsquery('russian', %s), 
                               'MaxWords=50, MinWords=30, ShortWord=3') as snippet
                FROM search_index si
                WHERE si.user_id = %s
                  AND si.search_vector @@ to_tsquery('russian', %s)
                ORDER BY rank DESC
                LIMIT %s;
                """,
                (search_query, search_query, user_id, search_query, limit)
            )
            
            for row in cur.fetchall():
                # psycopg2 автоматически десериализует JSONB в dict
                results.append({
                    'id': row[0],
                    'document_id': row[1],
                    'content': row[2],
                    'metadata': row[3] if row[3] else {},
                    'rank': float(row[4]) if row[4] else 0.0,
                    'snippet': row[5]
                })
        
        logger.info(f"Поиск по {len(keywords)} ключевым словам: найдено {len(results)} результатов")
        return results
    
    def simple_search(
        self,
        user_id: int,
        keywords: List[str],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Простой поиск по вхождению подстрок (fallback если tsvector не работает).
        
        Args:
            user_id: ID пользователя
            keywords: Список ключевых слов для поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список словарей с результатами поиска
        """
        if not keywords:
            return []
        
        results = []
        
        # Формируем условие LIKE для каждого ключевого слова
        like_conditions = ' OR '.join(['LOWER(si.content) LIKE %s'] * len(keywords))
        like_params = [f'%{kw.lower()}%' for kw in keywords]
        
        with self.db.cursor() as cur:
            query = f"""
                SELECT 
                    si.id,
                    si.document_id,
                    si.content,
                    si.metadata
                FROM search_index si
                WHERE si.user_id = %s
                  AND ({like_conditions})
                LIMIT %s;
            """
            
            params = [user_id] + like_params + [limit]
            cur.execute(query, params)
            
            for row in cur.fetchall():
                import json
                results.append({
                    'id': row[0],
                    'document_id': row[1],
                    'content': row[2],
                    'metadata': json.loads(row[3]) if row[3] else {},
                })
        
        logger.info(f"Простой поиск: найдено {len(results)} результатов")
        return results
    
    def delete_by_document(self, document_id: int) -> int:
        """
        Удаляет записи индекса для документа.
        
        Args:
            document_id: ID документа
            
        Returns:
            Количество удалённых записей
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                DELETE FROM search_index
                WHERE document_id = %s
                RETURNING id;
                """,
                (document_id,)
            )
            deleted_count = cur.rowcount
            
        logger.info(f"Удалено {deleted_count} записей индекса для документа {document_id}")
        return deleted_count
    
    def delete_by_user(self, user_id: int) -> int:
        """
        Удаляет все записи индекса пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество удалённых записей
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                DELETE FROM search_index
                WHERE user_id = %s
                RETURNING id;
                """,
                (user_id,)
            )
            deleted_count = cur.rowcount
            
        logger.info(f"Удалено {deleted_count} записей индекса для пользователя {user_id}")
        return deleted_count
    
    def get_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Получает статистику по поисковому индексу.
        
        Args:
            user_id: ID пользователя (если None - общая статистика)
            
        Returns:
            Словарь со статистикой
        """
        stats = {}
        
        with self.db.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_entries,
                        COUNT(DISTINCT document_id) as total_documents,
                        pg_size_pretty(pg_total_relation_size('search_index')) as table_size
                    FROM search_index
                    WHERE user_id = %s;
                    """,
                    (user_id,)
                )
            else:
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_entries,
                        COUNT(DISTINCT document_id) as total_documents,
                        COUNT(DISTINCT user_id) as total_users,
                        pg_size_pretty(pg_total_relation_size('search_index')) as table_size
                    FROM search_index;
                    """
                )
            
            row = cur.fetchone()
            if row:
                if user_id:
                    stats = {
                        'total_entries': row[0],
                        'total_documents': row[1],
                        'table_size': row[2]
                    }
                else:
                    stats = {
                        'total_entries': row[0],
                        'total_documents': row[1],
                        'total_users': row[2],
                        'table_size': row[3]
                    }
        
        return stats
