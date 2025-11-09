"""
Garbage Collector для управления хранилищем документов.

Реализует спецификацию 015:
- Мягкое удаление (is_visible=FALSE, deleted_at=NOW())
- Физическое удаление по retention score
- Автоматический и ручной режимы
- Логирование в storage_audit.log
"""
import os
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
from webapp.models.rag_models import RAGDatabase


# Настройка логгера для аудита хранилища
def get_storage_audit_logger(log_path: str = 'logs/storage_audit.log') -> logging.Logger:
    """
    Получить логгер для аудита операций со хранилищем.
    
    Args:
        log_path: Путь к файлу логов
        
    Returns:
        Настроенный логгер
    """
    logger = logging.getLogger('storage_audit')
    
    # Если уже настроен - возвращаем
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # Создаём папку для логов если не существует
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # Файловый хендлер с ротацией
    from logging.handlers import TimedRotatingFileHandler
    handler = TimedRotatingFileHandler(
        log_path,
        when='midnight',
        interval=1,
        backupCount=30,  # 30 дней истории
        encoding='utf-8'
    )
    handler.setLevel(logging.INFO)
    
    # Формат: время | уровень | сообщение
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger


def calculate_retention_score(
    is_visible: bool,
    deleted_at: datetime,
    last_accessed_at: datetime,
    access_count: int,
    indexing_cost_seconds: float,
    now: datetime = None
) -> float:
    """
    Вычисляет retention score для документа.
    
    Формула (из спецификации 015):
    score = -100 (если is_visible=FALSE и прошло >30 дней)
         OR 0.5 * log(access_count + 1) - 0.3 * days_since_access + 0.2 * indexing_cost_minutes
    
    Args:
        is_visible: Флаг видимости документа
        deleted_at: Дата мягкого удаления (или None)
        last_accessed_at: Дата последнего доступа (или None)
        access_count: Количество обращений к документу
        indexing_cost_seconds: Стоимость индексации в секундах
        now: Текущее время (для тестирования)
        
    Returns:
        Retention score (чем меньше - тем больше кандидат на удаление)
    """
    import math
    
    if now is None:
        now = datetime.now()
    
    # Случай 1: Невидимый документ (мягко удалён)
    if not is_visible:
        if deleted_at:
            days_deleted = (now - deleted_at).days
            if days_deleted > 30:
                return -100.0  # Однозначный кандидат на удаление
        return -50.0  # Удалён недавно - низкий приоритет
    
    # Случай 2: Видимый документ
    # Дефолтные значения если данных нет
    if last_accessed_at is None:
        days_since_access = 365  # Год как будто не использовался
    else:
        days_since_access = max(0, (now - last_accessed_at).days)
    
    access_factor = 0.5 * math.log(access_count + 1)
    recency_penalty = 0.3 * days_since_access
    cost_bonus = 0.2 * (indexing_cost_seconds / 60.0)  # переводим в минуты
    
    score = access_factor - recency_penalty + cost_bonus
    return score


def get_gc_candidates(
    db: RAGDatabase,
    threshold_score: float = -10.0,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Получить список кандидатов на удаление по retention score.
    
    Args:
        db: Подключение к БД
        threshold_score: Порог score (документы с score ниже - удаляются)
        limit: Максимальное количество кандидатов
        
    Returns:
        Список словарей с полями: id, owner_id, original_filename, score
    """
    candidates = []
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # CTE для вычисления retention score на лету
                cur.execute("""
                    WITH scored_docs AS (
                        SELECT 
                            id,
                            owner_id,
                            original_filename,
                            is_visible,
                            deleted_at,
                            last_accessed_at,
                            access_count,
                            indexing_cost_seconds,
                            CASE
                                WHEN NOT is_visible AND deleted_at IS NOT NULL 
                                     AND (EXTRACT(EPOCH FROM (NOW() - deleted_at)) / 86400) > 30
                                THEN -100.0
                                WHEN NOT is_visible
                                THEN -50.0
                                ELSE 
                                    0.5 * LN(COALESCE(access_count, 0) + 1)
                                    - 0.3 * GREATEST(0, EXTRACT(EPOCH FROM (NOW() - COALESCE(last_accessed_at, NOW() - INTERVAL '365 days'))) / 86400)
                                    + 0.2 * (COALESCE(indexing_cost_seconds, 0) / 60.0)
                            END AS retention_score
                        FROM documents
                    )
                    SELECT id, owner_id, original_filename, retention_score
                    FROM scored_docs
                    WHERE retention_score < %s
                    ORDER BY retention_score ASC
                    LIMIT %s;
                """, (threshold_score, limit))
                
                rows = cur.fetchall()
                for row in rows:
                    candidates.append({
                        'id': row[0],
                        'owner_id': row[1],
                        'original_filename': row[2],
                        'retention_score': float(row[3])
                    })
    except Exception as e:
        logging.exception(f'Ошибка получения кандидатов на GC: {e}')
    
    return candidates


def delete_documents(
    db: RAGDatabase,
    document_ids: List[int],
    audit_logger: logging.Logger = None
) -> Tuple[int, int]:
    """
    Физически удаляет документы и их чанки из БД.
    
    Args:
        db: Подключение к БД
        document_ids: Список ID документов для удаления
        audit_logger: Логгер для аудита (опционально)
        
    Returns:
        Tuple (удалено документов, удалено чанков)
    """
    if not document_ids:
        return 0, 0
    
    deleted_docs = 0
    deleted_chunks = 0
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Сначала удаляем чанки
                cur.execute("""
                    DELETE FROM chunks
                    WHERE document_id = ANY(%s);
                """, (document_ids,))
                deleted_chunks = cur.rowcount
                
                # Затем удаляем документы
                cur.execute("""
                    DELETE FROM documents
                    WHERE id = ANY(%s)
                    RETURNING id, original_filename, owner_id;
                """, (document_ids,))
                
                deleted_docs = cur.rowcount
                
                # Логируем удаления
                if audit_logger:
                    for row in cur.fetchall():
                        doc_id, filename, owner_id = row
                        audit_logger.info(
                            f"GC: Удалён документ #{doc_id} '{filename}' (owner_id={owner_id})"
                        )
            
            conn.commit()
    except Exception as e:
        logging.exception(f'Ошибка удаления документов: {e}')
    
    return deleted_docs, deleted_chunks


def run_garbage_collection(
    db: RAGDatabase,
    threshold_score: float = -10.0,
    max_deletions: int = 100,
    dry_run: bool = False,
    audit_log_path: str = 'logs/storage_audit.log'
) -> Dict[str, Any]:
    """
    Запускает сборку мусора (Garbage Collection).
    
    Args:
        db: Подключение к БД
        threshold_score: Порог retention score для удаления
        max_deletions: Максимальное количество удалений за раз
        dry_run: Если True - только показывает кандидатов, не удаляет
        audit_log_path: Путь к файлу аудита
        
    Returns:
        Статистика: {
            'candidates_found': int,
            'documents_deleted': int,
            'chunks_deleted': int,
            'dry_run': bool,
            'threshold_score': float
        }
    """
    audit_logger = get_storage_audit_logger(audit_log_path)
    start_time = datetime.now()
    
    # Ищем кандидатов
    candidates = get_gc_candidates(db, threshold_score, max_deletions)
    candidates_count = len(candidates)
    
    audit_logger.info(
        f"GC: Начало сборки мусора (threshold={threshold_score}, dry_run={dry_run}). "
        f"Найдено кандидатов: {candidates_count}"
    )
    
    if dry_run or candidates_count == 0:
        result = {
            'candidates_found': candidates_count,
            'documents_deleted': 0,
            'chunks_deleted': 0,
            'dry_run': dry_run,
            'threshold_score': threshold_score,
            'candidates': candidates[:20]  # Первые 20 для отладки
        }
        
        if dry_run and candidates_count > 0:
            audit_logger.info(
                f"GC: Dry-run завершён. Кандидаты на удаление: {candidates_count}"
            )
        
        return result
    
    # Удаляем кандидатов
    doc_ids = [c['id'] for c in candidates]
    docs_deleted, chunks_deleted = delete_documents(db, doc_ids, audit_logger)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    audit_logger.info(
        f"GC: Завершено. Удалено документов: {docs_deleted}, чанков: {chunks_deleted}. "
        f"Время: {elapsed:.2f}с"
    )
    
    return {
        'candidates_found': candidates_count,
        'documents_deleted': docs_deleted,
        'chunks_deleted': chunks_deleted,
        'dry_run': False,
        'threshold_score': threshold_score,
        'elapsed_seconds': elapsed
    }


def get_storage_stats(db: RAGDatabase) -> Dict[str, Any]:
    """
    Получить статистику использования хранилища.
    
    Returns:
        Словарь с полями:
        - total_documents: int
        - visible_documents: int
        - deleted_documents: int
        - total_chunks: int
        - total_users: int
        - avg_chunks_per_document: float
        - db_size_mb: float (если доступно)
    """
    stats = {
        'total_documents': 0,
        'visible_documents': 0,
        'deleted_documents': 0,
        'total_chunks': 0,
        'total_users': 0,
        'avg_chunks_per_document': 0.0
    }
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Статистика документов через user_documents (связь пользователей с документами)
                cur.execute("""
                    SELECT 
                        COUNT(DISTINCT ud.document_id) as total,
                        SUM(CASE WHEN NOT COALESCE(ud.is_soft_deleted, FALSE) THEN 1 ELSE 0 END) as visible,
                        SUM(CASE WHEN COALESCE(ud.is_soft_deleted, FALSE) THEN 1 ELSE 0 END) as deleted,
                        COUNT(DISTINCT ud.user_id) as users
                    FROM user_documents ud;
                """)
                row = cur.fetchone()
                if row:
                    stats['total_documents'] = row[0] or 0
                    stats['visible_documents'] = row[1] or 0
                    stats['deleted_documents'] = row[2] or 0
                    stats['total_users'] = row[3] or 0
                
                # Статистика чанков
                cur.execute("SELECT COUNT(*) FROM chunks;")
                stats['total_chunks'] = cur.fetchone()[0]
                
                # Средние чанки на документ
                if stats['total_documents'] > 0:
                    stats['avg_chunks_per_document'] = stats['total_chunks'] / stats['total_documents']
                
                # Размер БД (опционально, требует прав)
                try:
                    cur.execute("SELECT pg_database_size(current_database()) / 1024.0 / 1024.0;")
                    stats['db_size_mb'] = round(cur.fetchone()[0], 2)
                except Exception:
                    pass  # Нет прав или не PostgreSQL
                    
    except Exception as e:
        logging.exception(f'Ошибка получения статистики хранилища: {e}')
    
    return stats
