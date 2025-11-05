"""Blueprint для административной панели управления хранилищем."""
from flask import Blueprint, request, jsonify, current_app, render_template, g
from webapp.middleware.auth_middleware import require_role
from webapp.services.gc_service import (
    run_garbage_collection,
    get_storage_stats,
    get_storage_audit_logger
)
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _get_db() -> RAGDatabase:
    """Получить подключение к БД (кешируется в g)."""
    if 'db' not in g:
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        g.db = RAGDatabase(dsn)
    return g.db


@admin_bp.route('/storage')
@require_role('admin')
def storage_page():
    """
    Главная страница административной панели.
    
    Требует: роль 'admin'
    
    Разделы:
    - Статистика хранилища
    - Управление квотами
    - Garbage Collection
    - Экстренная блокировка загрузок
    - Просмотр логов аудита
    """
    return render_template('admin_storage.html')


@admin_bp.get('/storage/stats')
@require_role('admin')
def storage_stats():
    """
    Получить статистику использования хранилища.
    
    Требует: роль 'admin'
    
    Returns:
        JSON с полями:
        - total_documents: int
        - visible_documents: int
        - deleted_documents: int
        - total_chunks: int
        - total_users: int
        - avg_chunks_per_document: float
        - db_size_mb: float
        - config: dict (квоты, лимиты)
    """
    try:
        db = _get_db()
        stats = get_storage_stats(db)
        
        # Добавляем информацию о конфигурации
        config = get_config()
        stats['config'] = {
            'user_quota_gb': round(config.user_quota_bytes / (1024**3), 2),
            'db_storage_limit_gb': round(config.db_storage_limit_bytes / (1024**3), 2),
            'chunk_size_tokens': config.chunk_size_tokens,
            'chunk_overlap_tokens': config.chunk_overlap_tokens,
            'uploads_disabled': config.uploads_disabled
        }
        
        return jsonify(stats)
    except Exception as e:
        current_app.logger.exception('Ошибка получения статистики хранилища')
        return jsonify({'error': str(e)}), 500


@admin_bp.post('/gc/run')
@require_role('admin')
def run_gc():
    """
    Запустить Garbage Collection вручную.
    
    Требует: роль 'admin'
    
    Request JSON:
    {
        "threshold_score": float (default: -10.0),
        "max_deletions": int (default: 100),
        "dry_run": bool (default: false)
    }
    
    Returns:
        JSON с результатами GC:
        - candidates_found: int
        - documents_deleted: int
        - chunks_deleted: int
        - dry_run: bool
        - threshold_score: float
    """
    try:
        data = request.get_json() or {}
        threshold = data.get('threshold_score', -10.0)
        max_deletions = data.get('max_deletions', 100)
        dry_run = data.get('dry_run', False)
        
        # Валидация параметров
        if not isinstance(threshold, (int, float)):
            return jsonify({'error': 'threshold_score должен быть числом'}), 400
        if not isinstance(max_deletions, int) or max_deletions <= 0:
            return jsonify({'error': 'max_deletions должен быть положительным целым числом'}), 400
        if max_deletions > 1000:
            return jsonify({'error': 'max_deletions не может превышать 1000'}), 400
        
        db = _get_db()
        config = get_config()
        
        result = run_garbage_collection(
            db,
            threshold_score=threshold,
            max_deletions=max_deletions,
            dry_run=dry_run,
            audit_log_path=config.storage_audit_log
        )
        
        current_app.logger.info(
            f"GC запущен администратором: threshold={threshold}, dry_run={dry_run}, "
            f"удалено документов={result['documents_deleted']}"
        )
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.exception('Ошибка запуска GC')
        return jsonify({'error': str(e)}), 500


@admin_bp.get('/gc/candidates')
@require_role('admin')
def get_gc_candidates_endpoint():
    """
    Получить список кандидатов на удаление без фактического удаления.
    
    Требует: роль 'admin'
    
    Query params:
    - threshold: float (default: -10.0)
    - limit: int (default: 100)
    
    Returns:
        JSON с кандидатами: [{"id", "owner_id", "original_filename", "retention_score"}]
    """
    try:
        from webapp.services.gc_service import get_gc_candidates
        
        threshold = float(request.args.get('threshold', -10.0))
        limit = int(request.args.get('limit', 100))
        
        if limit > 500:
            return jsonify({'error': 'Лимит не может превышать 500'}), 400
        
        db = _get_db()
        candidates = get_gc_candidates(db, threshold, limit)
        
        return jsonify({
            'count': len(candidates),
            'threshold': threshold,
            'candidates': candidates
        })
    except Exception as e:
        current_app.logger.exception('Ошибка получения кандидатов GC')
        return jsonify({'error': str(e)}), 500


@admin_bp.post('/uploads/toggle')
@require_role('admin')
def toggle_uploads():
    """
    Экстренное включение/отключение загрузок.
    
    Требует: роль 'admin'
    
    Request JSON:
    {
        "enabled": bool
    }
    
    Returns:
        JSON: {"uploads_enabled": bool, "message": str}
    """
    try:
        data = request.get_json() or {}
        enabled = data.get('enabled')
        
        if not isinstance(enabled, bool):
            return jsonify({'error': 'Параметр enabled должен быть bool'}), 400
        
        config = get_config()
        # TODO: Сохранять изменение в конфиг или переменную окружения
        # Пока просто логируем
        
        action = 'включены' if enabled else 'отключены'
        current_app.logger.warning(f"Загрузки {action} администратором")
        
        audit_logger = get_storage_audit_logger(config.storage_audit_log)
        audit_logger.warning(f"ADMIN: Загрузки {action}")
        
        return jsonify({
            'uploads_enabled': enabled,
            'message': f'Загрузки {action}'
        })
    except Exception as e:
        current_app.logger.exception('Ошибка переключения загрузок')
        return jsonify({'error': str(e)}), 500


@admin_bp.get('/quota/<int:user_id>')
@require_role('admin')
def get_user_quota(user_id: int):
    """
    Получить информацию о квоте пользователя.
    
    Returns:
        JSON:
        - user_id: int
        - total_documents: int
        - total_size_bytes: int (сумма размеров файлов)
        - quota_bytes: int (из конфига)
        - quota_used_percent: float
    """
    try:
        db = _get_db()
        config = get_config()
        
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Подсчёт документов и размера (приблизительный через indexing_cost)
                cur.execute("""
                    SELECT 
                        COUNT(*) as doc_count,
                        SUM(COALESCE(indexing_cost_seconds, 0)) as total_cost
                    FROM documents
                    WHERE owner_id = %s AND is_visible = TRUE;
                """, (user_id,))
                row = cur.fetchone()
                doc_count = row[0] if row else 0
                total_cost = row[1] if row and row[1] else 0.0
        
        # Приблизительная оценка размера: 1 секунда индексации ≈ 1 МБ текста
        estimated_size_bytes = int(total_cost * 1024 * 1024)
        quota_bytes = config.user_quota_bytes
        quota_used_percent = (estimated_size_bytes / quota_bytes * 100) if quota_bytes > 0 else 0.0
        
        return jsonify({
            'user_id': user_id,
            'total_documents': doc_count,
            'total_size_bytes': estimated_size_bytes,
            'quota_bytes': quota_bytes,
            'quota_used_percent': round(quota_used_percent, 2)
        })
    except Exception as e:
        current_app.logger.exception(f'Ошибка получения квоты для user_id={user_id}')
        return jsonify({'error': str(e)}), 500


@admin_bp.get('/config')
@require_role('admin')
def get_admin_config():
    """
    Получить текущую конфигурацию административных параметров.
    
    Требует: роль 'admin'
    
    Returns:
        JSON: {"uploads_disabled": bool, ...}
    """
    try:
        config = get_config()
        return jsonify({
            'uploads_disabled': config.uploads_disabled,
            'user_quota_bytes': config.user_quota_bytes,
            'db_storage_limit_bytes': config.db_storage_limit_bytes,
            'chunk_size_tokens': config.chunk_size_tokens,
            'chunk_overlap_tokens': config.chunk_overlap_tokens
        })
    except Exception as e:
        current_app.logger.exception('Ошибка получения конфигурации')
        return jsonify({'error': str(e)}), 500


@admin_bp.get('/audit_log')
@require_role('admin')
def get_audit_log():
    """
    Получить последние записи из лога аудита.
    
    Требует: роль 'admin'
    
    Query params:
    - limit: int (default: 100, max: 1000)
    
    Returns:
        JSON: {"logs": [{"timestamp": "...", "level": "info", "message": "..."}], ...}
    """
    try:
        config = get_config()
        limit = int(request.args.get('limit', 100))
        limit = min(limit, 1000)
        
        import os
        import re
        from datetime import datetime
        
        log_path = config.storage_audit_log
        
        if not os.path.exists(log_path):
            return jsonify({'logs': [], 'message': 'Лог-файл не существует'})
        
        # Читаем последние N строк
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-limit:] if len(all_lines) > limit else all_lines
        
        # Парсим строки лога
        logs = []
        log_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.+)')
        
        for line in last_lines:
            match = log_pattern.match(line.strip())
            if match:
                timestamp_str, level, message = match.groups()
                logs.append({
                    'timestamp': timestamp_str,
                    'level': level.lower(),
                    'message': message
                })
            else:
                # Строки без стандартного формата
                logs.append({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'info',
                    'message': line.strip()
                })
        
        return jsonify({
            'logs': logs,
            'total_lines': len(all_lines),
            'returned': len(logs)
        })
    except Exception as e:
        current_app.logger.exception('Ошибка чтения лога аудита')
        return jsonify({'error': str(e)}), 500
