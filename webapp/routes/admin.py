"""Blueprint для административной панели управления хранилищем."""
from flask import Blueprint, request, jsonify, current_app, render_template, g
import threading
import time
import os
from webapp.middleware.auth_middleware import require_role
from webapp.services.gc_service import (
    run_garbage_collection,
    get_storage_stats,
    get_storage_audit_logger
)
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config
from psycopg2 import sql

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
                        SUM(COALESCE(d.indexing_cost_seconds, 0)) as total_cost
                    FROM user_documents ud
                    JOIN documents d ON d.id = ud.document_id
                    WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE;
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


# [ИНКРЕМЕНТ 020 - Блок 8] Эндпоинты планировщика удалены.
# APScheduler для периодического GC больше не используется.
# Prune происходит автоматически при загрузке файлов (on-write enforcement).
# Настройки прунинга теперь в /admin/settings (AUTO_PRUNE_ENABLED, DB_SIZE_LIMIT_BYTES).


# ===== Очистка БД (UI + API) =====

@admin_bp.get('/db/cleanup')
@require_role('admin')
def db_cleanup_page():
    """Страница с чекбоксами для очистки выбранных таблиц."""
    return render_template('admin_cleanup_db.html')


@admin_bp.get('/db/tables')
@require_role('admin')
def db_list_tables():
    """Вернуть список всех таблиц schema=public с примерной статистикой (кол-во строк и размер)."""
    try:
        db = _get_db()
        tables = []
        protected = {'users', 'alembic_version', 'roles', 'sessions'}  # базовые таблицы, не чистим по умолчанию
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tablename FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename;
                """)
                names = [r[0] for r in cur.fetchall()]
            # Подсчёт строк и размера по-отдельности
            with conn.cursor() as cur:
                for name in names:
                    row_count = None
                    size_str = None
                    try:
                        cur.execute(sql.SQL('SELECT COUNT(*) FROM {};').format(sql.Identifier(name)))
                        row_count = cur.fetchone()[0]
                    except Exception:
                        row_count = None
                    
                    try:
                        # Получаем размер таблицы с индексами в байтах
                        cur.execute(sql.SQL("SELECT pg_total_relation_size({});").format(sql.Literal(name)))
                        size_bytes = cur.fetchone()[0]
                        if size_bytes is not None:
                            # Форматируем в МБ/ГБ
                            if size_bytes < 1024 * 1024:  # < 1 МБ
                                size_str = f"{size_bytes / 1024:.1f} КБ"
                            elif size_bytes < 1024 * 1024 * 1024:  # < 1 ГБ
                                size_str = f"{size_bytes / (1024 * 1024):.1f} МБ"
                            else:
                                size_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} ГБ"
                    except Exception:
                        size_str = None
                    
                    tables.append({
                        'name': name,
                        'rows': row_count,
                        'size': size_str,
                        'protected': name in protected
                    })
        return jsonify({'tables': tables})
    except Exception:
        current_app.logger.exception('Ошибка получения списка таблиц БД')
        return jsonify({'error': 'Не удалось получить список таблиц'}), 500


@admin_bp.post('/db/cleanup')
@require_role('admin')
def db_cleanup_run():
    """Очистить выбранные таблицы через TRUNCATE ... RESTART IDENTITY CASCADE.

    Body JSON: {"tables": ["name1", ...], "preserve_prompts": true/false}
    """
    try:
        data = request.get_json() or {}
        requested: list = data.get('tables') or []
        preserve_prompts: bool = bool(data.get('preserve_prompts', True))
        if not isinstance(requested, list) or not all(isinstance(t, str) for t in requested):
            return jsonify({'error': 'Неверный формат: ожидался список имён таблиц'}), 400
        if not requested:
            return jsonify({'error': 'Не выбраны таблицы для очистки'}), 400

        db = _get_db()
        with db.db.connect() as conn:
            # Получаем список существующих таблиц
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tablename FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public';
                """)
                existing = {r[0] for r in cur.fetchall()}

            # Фильтруем к очистке
            to_truncate = [t for t in requested if t in existing]
            skipped = [t for t in requested if t not in existing]

            # Уважение флага сохранения prompts
            if preserve_prompts and 'prompts' in to_truncate:
                to_truncate.remove('prompts')

            if not to_truncate:
                return jsonify({'error': 'Нет валидных таблиц для очистки', 'skipped': skipped}), 400

            before = {}
            after = {}
            # Подсчёт до
            with conn.cursor() as cur:
                for name in to_truncate:
                    try:
                        cur.execute(sql.SQL('SELECT COUNT(*) FROM {};').format(sql.Identifier(name)))
                        before[name] = cur.fetchone()[0]
                    except Exception:
                        before[name] = None

            # Выполняем TRUNCATE
            with conn.cursor() as cur:
                stmt = sql.SQL('TRUNCATE TABLE {} RESTART IDENTITY CASCADE;').format(
                    sql.SQL(', ').join(sql.Identifier(n) for n in to_truncate)
                )
                cur.execute(stmt)
            conn.commit()

            # Подсчёт после
            with conn.cursor() as cur:
                for name in to_truncate:
                    try:
                        cur.execute(sql.SQL('SELECT COUNT(*) FROM {};').format(sql.Identifier(name)))
                        after[name] = cur.fetchone()[0]
                    except Exception:
                        after[name] = None

        return jsonify({
            'truncated': to_truncate,
            'skipped': skipped,
            'preserve_prompts': preserve_prompts,
            'before': before,
            'after': after,
            'message': 'Очистка выполнена'
        })
    except Exception:
        current_app.logger.exception('Ошибка очистки таблиц БД')
        return jsonify({'error': 'Не удалось выполнить очистку'}), 500


# ===== Перезагрузка сервера =====

@admin_bp.post('/server/restart')
@require_role('admin')
def server_restart():
    """Запланировать перезагрузку сервера.

    Т.к. текущий процесс держит порт, прямая попытка освободить его сразу
    внутри запроса может убить соединение до ответа. Поэтому используем
    отложенный фоновой поток: возвращаем ответ клиенту, затем через небольшую
    паузу выполняем перезагрузку (освобождение порта + запуск новой команды) и
    завершаем текущий процесс.

    JSON Body (опционально): {"port": 5000, "command": ".venv/bin/python app.py", "wait": 2.5}
    Если параметры не переданы, применяются дефолты.
    """
    try:
        data = request.get_json(silent=True) or {}
        port = int(data.get('port', 5000))
        start_command = data.get('command', '.venv/bin/python app.py')
        wait_time = float(data.get('wait', 2.5))

        if port <= 0 or port > 65535:
            return jsonify({'error': 'Некорректный порт'}), 400
        if not isinstance(start_command, str) or not start_command.strip():
            return jsonify({'error': 'Команда запуска должна быть непустой строкой'}), 400

        current_app.logger.warning(f"Администратор инициировал перезагрузку сервера: port={port}, cmd={start_command}")

        def _delayed_restart():
            try:
                from restart_server import ServerReloader
                # Небольшая пауза, чтобы ответ успел уйти клиенту
                time.sleep(0.5)
                reloader = ServerReloader(port=port, start_command=start_command, wait_time=wait_time)
                reloader.restart()
            except Exception:
                current_app.logger.exception('Ошибка фоновой перезагрузки сервера')
            finally:
                # Завершаем текущий процесс Flask после попытки запуска нового
                try:
                    current_app.logger.info('Текущий процесс завершается после перезагрузки')
                except Exception:
                    pass
                os._exit(0)  # жёсткое завершение, чтобы порт освободился

        threading.Thread(target=_delayed_restart, daemon=True).start()

        return jsonify({
            'status': 'scheduled',
            'port': port,
            'command': start_command,
            'wait_time': wait_time,
            'message': 'Перезагрузка запланирована; сервер будет перезапущен через ~0.5s'
        })
    except Exception:
        current_app.logger.exception('Ошибка планирования перезагрузки')
        return jsonify({'error': 'Не удалось запланировать перезагрузку'}), 500


@admin_bp.route('/settings', methods=['GET'])
@require_role('admin')
def admin_prune_settings():
    """
    Страница настроек автоматической очистки БД.
    
    Требует: роль 'admin'
    
    Показывает:
    - Тумблер включения/отключения автоочистки
    - Поле ввода лимита размера БД (в ГБ/МБ)
    - Текущую статистику БД (размер, кол-во документов)
    """
    try:
        db = _get_db()
        config = get_config()
        
        # Читаем текущие настройки из app_settings
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM app_settings WHERE key IN ('AUTO_PRUNE_ENABLED', 'DB_SIZE_LIMIT_BYTES')")
                settings_rows = cur.fetchall()
        
        settings_dict = {row[0]: row[1] for row in settings_rows}
        auto_prune_enabled = settings_dict.get('AUTO_PRUNE_ENABLED', 'true').lower() == 'true'
        db_size_limit_bytes = int(settings_dict.get('DB_SIZE_LIMIT_BYTES', str(10 * 1024**3)))
        
        # Конвертируем в ГБ для удобства отображения
        size_limit_gb = round(db_size_limit_bytes / (1024**3), 2)
        
        # Получаем текущую статистику БД
        from webapp.services.gc_service import get_storage_stats
        stats = get_storage_stats(db)
        
        total_docs = stats.get('total_documents', 0)
        total_size_bytes = stats.get('db_size_mb', 0) * 1024 * 1024  # конвертируем МБ → байты
        total_size_mb = round(total_size_bytes / (1024**2), 2)
        total_size_gb = round(total_size_bytes / (1024**3), 2)
        usage_percent = round((total_size_bytes / db_size_limit_bytes * 100), 1) if db_size_limit_bytes > 0 else 0
        
        return render_template(
            'admin_settings.html',
            settings={
                'auto_prune_enabled': auto_prune_enabled,
                'size_limit_gb': size_limit_gb,
                'size_limit_bytes': db_size_limit_bytes
            },
            stats={
                'total_docs': total_docs,
                'total_size_mb': total_size_mb,
                'total_size_gb': total_size_gb,
                'usage_percent': usage_percent
            }
        )
    except Exception as e:
        current_app.logger.exception('Ошибка отображения страницы настроек прунинга')
        return f'Ошибка загрузки настроек: {str(e)}', 500


@admin_bp.route('/settings/prune', methods=['POST'])
@require_role('admin')
def admin_save_prune_settings():
    """
    Сохранить настройки автоматической очистки БД.
    
    Требует: роль 'admin'
    
    Form data:
    - auto_prune_enabled: checkbox (on/off)
    - size_limit: float (число)
    - size_unit: str ('gb' или 'mb')
    
    Сохраняет в app_settings таблицу:
    - AUTO_PRUNE_ENABLED: 'true' / 'false'
    - DB_SIZE_LIMIT_BYTES: int (конвертированный лимит)
    """
    try:
        db = _get_db()
        
        # Получаем данные из формы
        auto_prune_enabled = request.form.get('auto_prune_enabled') == 'on'
        size_limit_str = request.form.get('size_limit', '10')
        size_unit = request.form.get('size_unit', 'gb')
        
        # Валидация и конвертация размера
        try:
            size_limit = float(size_limit_str)
            if size_limit <= 0:
                raise ValueError("Размер должен быть положительным")
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f'Некорректный размер лимита: {size_limit_str}')
            return f'Ошибка: некорректное значение размера ({str(e)})', 400
        
        # Конвертируем в байты
        if size_unit == 'mb':
            size_limit_bytes = int(size_limit * 1024 * 1024)
        else:  # gb
            size_limit_bytes = int(size_limit * 1024 * 1024 * 1024)
        
        # Минимальный лимит: 100 МБ
        if size_limit_bytes < 100 * 1024 * 1024:
            return 'Ошибка: минимальный размер БД — 100 МБ', 400
        
        # Сохраняем в app_settings через UPSERT
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app_settings (key, value)
                    VALUES ('AUTO_PRUNE_ENABLED', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, ('true' if auto_prune_enabled else 'false',))
                
                cur.execute("""
                    INSERT INTO app_settings (key, value)
                    VALUES ('DB_SIZE_LIMIT_BYTES', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (str(size_limit_bytes),))
            conn.commit()
        
        current_app.logger.info(
            f"Настройки прунинга обновлены администратором: "
            f"enabled={auto_prune_enabled}, limit={size_limit_bytes} bytes"
        )
        
        # Редирект обратно на страницу настроек с сообщением успеха
        from flask import redirect, url_for, flash
        flash('Настройки успешно сохранены', 'success')
        return redirect(url_for('admin.admin_prune_settings'))
        
    except Exception as e:
        current_app.logger.exception('Ошибка сохранения настроек прунинга')
        return f'Ошибка сохранения настроек: {str(e)}', 500
