from typing import Tuple
import logging

logger = logging.getLogger('webapp.db_gc')


def prune_low_score_documents(conn, limit_bytes: int) -> Tuple[int, int]:
    """Удалить нижние 30% документов по retention score, пока суммарный size_bytes > limit_bytes.

    Args:
        conn: psycopg2 connection (или объект с cursor())
        limit_bytes: порог в байтах

    Returns:
        Tuple[deleted_count, remaining_bytes]
    """
    try:
        cur = conn.cursor()
        # Суммарный размер
        cur.execute("SELECT COALESCE(SUM(size_bytes),0) FROM documents WHERE is_visible = TRUE;")
        total = cur.fetchone()[0] or 0
        logger.info(f'[PRUNE] Текущий объём БД (size_bytes): {total} bytes, лимит: {limit_bytes} bytes')
        if total <= limit_bytes:
            return 0, total

        # Вычисляем ранжирование и удаляем нижние 30% от видимых
        cur.execute("""
        WITH ranked AS (
            SELECT d.id,
                   (
                     0.5 * LN(COALESCE(d.access_count,0) + 1)
                     - 0.3 * EXTRACT(EPOCH FROM (NOW() - COALESCE(d.last_accessed_at, d.created_at)))/86400.0
                     + 0.2 * (COALESCE(d.indexing_cost_seconds, 0) / 60.0)
                   ) AS score,
                   ROW_NUMBER() OVER (ORDER BY (
                     0.5 * LN(COALESCE(d.access_count,0) + 1)
                     - 0.3 * EXTRACT(EPOCH FROM (NOW() - COALESCE(d.last_accessed_at, d.created_at)))/86400.0
                     + 0.2 * (COALESCE(d.indexing_cost_seconds, 0) / 60.0)
                   ) ASC) AS rn,
                   COUNT(*) OVER () AS total
            FROM documents d
            WHERE d.is_visible = TRUE
        )
        DELETE FROM documents d
        USING ranked r
        WHERE d.id = r.id
          AND r.rn <= GREATEST(1, FLOOR(0.3 * r.total)::BIGINT)
        RETURNING d.id, d.size_bytes;
        """)
        deleted = cur.fetchall()
        deleted_count = len(deleted)
        deleted_bytes = sum([r[1] or 0 for r in deleted])
        conn.commit()
        # Обновляем финальный объём
        cur.execute("SELECT COALESCE(SUM(size_bytes),0) FROM documents WHERE is_visible = TRUE;")
        remaining = cur.fetchone()[0] or 0
        logger.info(f'[PRUNE] Удалено документов: {deleted_count}, байт: {deleted_bytes}. Осталось: {remaining} bytes')
        return deleted_count, remaining
    except Exception as e:
        logger.exception('Ошибка при prune')
        try:
            conn.rollback()
        except Exception:
            pass
        raise
