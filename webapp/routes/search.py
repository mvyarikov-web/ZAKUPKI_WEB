"""Blueprint для поиска и индексации."""
import os
import re
import json
import html as htmllib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app, Response, g
from webapp.services.files import allowed_file
from webapp.services.state import FilesState
from webapp.services.indexing import get_index_path
from webapp.services.db_indexing import build_db_index
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config

search_bp = Blueprint('search', __name__)


def _get_db() -> RAGDatabase:
    """Получить подключение к БД (кешируется в g)."""
    if 'db' not in g:
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        g.db = RAGDatabase(dsn)
    return g.db


def _get_current_user_id() -> int:
    """
    Получить ID текущего пользователя из сессии/токена.
    
    TODO: Интеграция с реальной системой аутентификации.
    Пока возвращаем фиксированный ID для разработки.
    """
    # Заглушка: в будущем извлечь из JWT токена или сессии
    return g.get('user_id', 1)  # default owner_id=1 для dev


def _search_in_db(db: RAGDatabase, owner_id: int, keywords: list, exclude_mode: bool = False) -> list:
    """
    Поиск по чанкам в БД с фильтрацией по owner_id и is_visible.
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        keywords: Список ключевых слов
        exclude_mode: Если True, ищет файлы БЕЗ ключевых слов
        
    Returns:
        Список результатов поиска
    """
    results = []
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Формируем tsquery для полнотекстового поиска
                query_terms = ' | '.join(keywords)  # OR между терминами
                
                if exclude_mode:
                    # Ищем документы, где НИ ОДИН термин не встречается
                    cur.execute("""
                        SELECT DISTINCT d.id, d.original_filename
                        FROM documents d
                        WHERE d.owner_id = %s
                          AND d.is_visible = TRUE
                          AND NOT EXISTS (
                              SELECT 1 FROM chunks c
                              WHERE c.document_id = d.id
                                AND to_tsvector('russian', c.text) @@ to_tsquery('russian', %s)
                          );
                    """, (owner_id, query_terms))
                    
                    rows = cur.fetchall()
                    for row in rows:
                        results.append({
                            'file': row[1],
                            'matches': [],
                            'match_count': 0,
                            'status': 'no_match'
                        })
                else:
                    # Обычный поиск: ищем чанки с совпадениями
                    cur.execute("""
                        SELECT 
                            d.id,
                            d.original_filename,
                            c.chunk_idx,
                            c.text,
                            ts_headline('russian', c.text, to_tsquery('russian', %s), 'MaxWords=20, MinWords=10') as snippet
                        FROM documents d
                        JOIN chunks c ON c.document_id = d.id
                        WHERE d.owner_id = %s
                          AND d.is_visible = TRUE
                          AND to_tsvector('russian', c.text) @@ to_tsquery('russian', %s)
                        ORDER BY d.original_filename, c.chunk_idx
                        LIMIT 500;
                    """, (query_terms, owner_id, query_terms))
                    
                    rows = cur.fetchall()
                    
                    # Группируем по файлам
                    file_matches = {}
                    for row in rows:
                        doc_id, filename, chunk_idx, text, snippet = row
                        
                        if filename not in file_matches:
                            file_matches[filename] = {
                                'file': filename,
                                'matches': [],
                                'match_count': 0,
                                'doc_id': doc_id
                            }
                        
                        file_matches[filename]['matches'].append({
                            'chunk_idx': chunk_idx,
                            'snippet': snippet,
                            'text': text[:200]  # ограничиваем для производительности
                        })
                        file_matches[filename]['match_count'] += 1
                    
                    results = list(file_matches.values())
                    
    except Exception:
        current_app.logger.exception("Ошибка поиска в БД")
        raise
    
    return results


def _update_document_access_metrics(db: RAGDatabase, results: list) -> None:
    """
    Обновляет метрики использования документов (access_count, last_accessed_at).
    
    Args:
        db: Подключение к БД
        results: Список результатов поиска
    """
    if not results:
        return
    
    try:
        doc_ids = [r.get('doc_id') for r in results if r.get('doc_id')]
        if not doc_ids:
            return
        
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documents
                    SET access_count = access_count + 1,
                        last_accessed_at = CURRENT_TIMESTAMP
                    WHERE id = ANY(%s);
                """, (doc_ids,))
            conn.commit()
            
        current_app.logger.debug(f"Обновлены метрики для {len(doc_ids)} документов")
        
    except Exception as e:
        current_app.logger.warning(f"Не удалось обновить метрики использования: {e}")


    conn.commit()


def _get_files_state():
    """Получить экземпляр FilesState для текущего приложения."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@search_bp.route('/search', methods=['POST'])
def search():
    """Поиск по ключевым словам (спецификация 015).
    
    Поиск всегда происходит в БД с фильтрацией по owner_id и is_visible=TRUE.
    Legacy файловый индекс больше не поддерживается.
    """
    search_terms = request.json.get('search_terms', '')
    exclude_mode = request.json.get('exclude_mode', False)
    
    if not search_terms.strip():
        return jsonify({'error': 'Введите ключевые слова для поиска'}), 400
    
    # Валидация: не более 10 терминов, длина 2..64, удаление дубликатов
    raw_terms = [t.strip() for t in search_terms.split(',') if t.strip()]
    if len(raw_terms) > 50:  # жёсткий предел на вход
        raw_terms = raw_terms[:50]
    filtered = []
    seen = set()
    for t in raw_terms[:10]:
        if 2 <= len(t) <= 64 and t.lower() not in seen:
            seen.add(t.lower())
            filtered.append(t)
    if not filtered:
        return jsonify({'error': 'Слишком короткие/длинные или пустые ключевые слова'}), 400

    current_app.logger.info(f"Поиск в БД: terms='{','.join(filtered)}', exclude_mode={exclude_mode}")
    
    db = _get_db()
    owner_id = _get_current_user_id()
    
    try:
        # Поиск с фильтрацией по owner_id и is_visible=TRUE
        results = _search_in_db(db, owner_id, filtered, exclude_mode)
        
        # Обновляем метрики использования (access_count, last_accessed_at)
        _update_document_access_metrics(db, results)
        
        current_app.logger.info(f"Поиск в БД завершён: найдено {len(results)} результатов")
        return jsonify({'results': results})
        
    except Exception as e:
        current_app.logger.exception("Ошибка поиска в БД")
        return jsonify({'error': f'Ошибка поиска: {str(e)}'}), 500


def _parse_index_groups(index_path: str) -> dict:
    """Парсит индекс и извлекает информацию о группах.
    
    Returns:
        {
            'fast': {'files': 50, 'completed': True, 'size_bytes': 12345},
            'medium': {'files': 30, 'completed': False, 'size_bytes': 0},
            'slow': {'files': 10, 'completed': False, 'size_bytes': 0}
        }
    """
    groups_info = {}
    
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for group_name in ['fast', 'medium', 'slow']:
            # Ищем заголовок группы
            group_pattern = rf'\[ГРУППА: {group_name.upper()}\].*?Файлов: (\d+).*?Статус: ([^\n]+)'
            match = re.search(group_pattern, content, re.IGNORECASE | re.DOTALL)
            
            if match:
                files_count = int(match.group(1))
                status_text = match.group(2).strip()
                completed = '✅' in status_text or 'завершено' in status_text.lower()
                
                # Вычисляем размер контента группы
                begin_marker = f'<!-- BEGIN_{group_name.upper()} -->'
                end_marker = f'<!-- END_{group_name.upper()} -->'
                group_content = re.search(
                    re.escape(begin_marker) + r'(.*?)' + re.escape(end_marker),
                    content,
                    re.DOTALL
                )
                size_bytes = len(group_content.group(1).strip()) if group_content else 0
                
                groups_info[group_name] = {
                    'files': files_count,
                    'completed': completed,
                    'size_bytes': size_bytes
                }
    except Exception as e:
        current_app.logger.warning(f"Ошибка парсинга групп индекса: {e}")
    
    return groups_info


@search_bp.route('/build_index', methods=['POST'])
def build_index_route():
    """Явная сборка индекса по папке uploads (спецификация 015).
    
    Индексация всегда происходит в БД с инкрементальностью.
    Legacy файловый индекс больше не поддерживается.
    """
    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        return jsonify({'success': False, 'message': 'Папка uploads не найдена'}), 400
    
    config = get_config()
    
    try:
        current_app.logger.info("Запуск индексации в БД (increment-015)")
        
        db = _get_db()
        owner_id = _get_current_user_id()
        
        success, message, stats = build_db_index(
            db=db,
            owner_id=owner_id,
            folder_path=uploads,
            chunk_size_tokens=config.chunk_size_tokens,
            chunk_overlap_tokens=config.chunk_overlap_tokens
        )
        
        if not success:
            current_app.logger.error(f"Ошибка индексации в БД: {message}")
            return jsonify({'success': False, 'message': message}), 500
        
        current_app.logger.info(f"Индексация в БД завершена: {message}")
        return jsonify({
            'success': True,
            'message': message,
            'stats': stats
        })
        
    
    except Exception as e:
        current_app.logger.exception("Ошибка при сборке индекса")
        return jsonify({'success': False, 'message': str(e)}), 500


@search_bp.get('/index_status')
def index_status():
    """Возвращает статус индексации и информацию о группах.
    
    Returns:
        JSON с полями:
        - status: idle | running | completed | error
        - group_status: {fast: pending|running|completed, medium: ..., slow: ...}
        - current_group: fast | medium | slow (если running)
        - index_exists: bool
        - index_size: int (байты)
        - groups_info: {fast: {files: int, completed: bool}, ...}
    """
    try:
        # Проверяем наличие progress status файла (increment-013/014)
        index_folder = current_app.config.get('INDEX_FOLDER')
        status_json_path = os.path.join(index_folder, 'status.json') if index_folder else None
        progress_data = None
        
        if status_json_path and os.path.exists(status_json_path):
            try:
                import json
                with open(status_json_path, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
            except Exception as e:
                current_app.logger.debug("Не удалось прочитать status.json: %s", e)
        
        # Если в текущей папке uploads нет поддерживаемых файлов, считаем индекс отсутствующим
        uploads = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        has_files = False
        if os.path.exists(uploads):
            for root, dirs, files in os.walk(uploads):
                for fname in files:
                    if fname == '_search_index.txt' or fname.startswith('~$') or fname.startswith('$'):
                        continue
                    if allowed_file(fname, current_app.config['ALLOWED_EXTENSIONS']):
                        has_files = True
                        break
                if has_files:
                    break
        
        if not has_files:
            response = {'exists': False}
            if progress_data:
                response['progress'] = progress_data
            return jsonify(response)

        # Резолвим актуальный индекс (index/ или uploads/)
        idx_primary = get_index_path(current_app.config['INDEX_FOLDER'])
        idx_uploads = os.path.join(uploads, '_search_index.txt')
        idx = idx_primary if os.path.exists(idx_primary) else (idx_uploads if os.path.exists(idx_uploads) else idx_primary)
        exists = os.path.exists(idx)
        
        if not exists:
            response = {'exists': False, 'index_exists': False}
            if progress_data:
                response['progress'] = progress_data
                # Добавляем статусы из progress_data на верхний уровень
                response['status'] = progress_data.get('status', 'idle')
                response['group_status'] = progress_data.get('group_status', {})
                response['current_group'] = progress_data.get('current_group')
            else:
                response['status'] = 'idle'
            return jsonify(response)
        
        size = os.path.getsize(idx)
        mtime = datetime.fromtimestamp(os.path.getmtime(idx)).isoformat()
        
        # Подсчёт записей (количество разделителей ===)
        try:
            with open(idx, 'r', encoding='utf-8', errors='ignore') as f:
                entries = sum(1 for line in f if line.strip().startswith('====='))
        except Exception:
            entries = None
        
        response = {
            'exists': True,
            'index_exists': True,
            'index_size': size,
            'size': size,
            'mtime': mtime,
            'entries': entries
        }
        
        # Парсим группы из индекса
        groups_info = _parse_index_groups(idx) if exists else {}
        if groups_info:
            response['groups_info'] = groups_info
        
        # Добавляем информацию о прогрессе если доступна
        if progress_data:
            response['progress'] = progress_data
            # Добавляем статусы из progress_data на верхний уровень
            prog_status = progress_data.get('status', 'completed')
            # Если индекс существует и статус в progress_data 'running', но индекс уже полный,
            # значит индексация завершилась — показываем completed
            if prog_status == 'running' and entries and entries > 0:
                # Проверяем timestamp: если статус не обновлялся > 10 секунд, считаем завершённым
                try:
                    updated_at = progress_data.get('updated_at')
                    if updated_at:
                        last_update = datetime.fromisoformat(updated_at)
                        if datetime.now() - last_update > timedelta(seconds=10):
                            prog_status = 'completed'
                except Exception:
                    pass
            response['status'] = prog_status
            response['group_status'] = progress_data.get('group_status', {})
            response['current_group'] = progress_data.get('current_group')
        else:
            response['status'] = 'idle'
        
        return jsonify(response)
    
    except Exception as e:
        current_app.logger.exception('Ошибка получения статуса индекса')
        return jsonify({'error': str(e)}), 500


@search_bp.get('/view_index')
def view_index():
    """Просмотр сводного файла индекса с автообновлением.
    
    Поддерживает query-параметры:
    - raw=1: показать индекс как есть (с заголовками групп)
    - raw=0 (default): показать только записи документов (без служебных строк)
    """
    # Показываем живой индекс из index/ или uploads/
    uploads = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    idx_primary = get_index_path(current_app.config['INDEX_FOLDER'])
    idx_uploads = os.path.join(uploads, '_search_index.txt')
    idx = idx_primary if os.path.exists(idx_primary) else (idx_uploads if os.path.exists(idx_uploads) else idx_primary)
    
    try:
        content = None
        if os.path.exists(idx):
            try:
                with open(idx, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                # Во время атомарной замены файл может быть временно недоступен
                content = None

        # Если не удалось прочитать индекс — формируем скелет по статусу
        if content is None:
            # Загружаем прогресс статуса
            progress = None
            status_json_path = os.path.join(current_app.config.get('INDEX_FOLDER'), 'status.json')
            try:
                if status_json_path and os.path.exists(status_json_path):
                    with open(status_json_path, 'r', encoding='utf-8') as sf:
                        progress = json.load(sf)
            except Exception:
                progress = None

            group_labels = {
                'fast': 'TXT, CSV, HTML',
                'medium': 'DOCX, XLSX, векторные PDF',
                'slow': 'PDF-сканы с OCR'
            }
            def map_status(s):
                if s == 'completed':
                    return '✅ завершено'
                if s == 'running':
                    return 'обрабатывается'
                return 'ожидание'
            grp_status = (progress or {}).get('group_status', {}) if progress else {}
            # Собираем скелет: заголовки + пустые секции между маркерами
            parts = []
            for g in ['fast', 'medium', 'slow']:
                parts.append('' )
                parts.append('═' * 80)
                parts.append(f"[ГРУППА: {g.upper()}] {group_labels[g]}")
                status_text = map_status(grp_status.get(g)) if grp_status else 'ожидание'
                parts.append(f"Файлов: — | Статус: {status_text}")
                parts.append('═' * 80)
                parts.append(f"<!-- BEGIN_{g.upper()} -->")
                parts.append(f"<!-- END_{g.upper()} -->")
                parts.append('')
            content = "\n".join(parts)
        
        # Добавляем метаинформацию в начало
        metadata = [
            "# Сводный индекс поиска",
            f"# Размер: {len(content)} байт",
            f"# Обновлён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "#",
            "# Формат: групповая структура (increment-014)",
            "# Группы: FAST (TXT,CSV,HTML) → MEDIUM (DOCX,XLSX,PDF) → SLOW (OCR)",
            "#",
            ""
        ]
        
        # Парсим статистику групп
        groups_info = _parse_index_groups(idx)
        for group_name, info in groups_info.items():
            status = "✅ завершено" if info['completed'] else "⏳ обрабатывается"
            metadata.append(
                f"# {group_name.upper()}: {info['files']} файлов, "
                f"{info['size_bytes']} байт, {status}"
            )
        
        metadata.append("#\n" + "=" * 80 + "\n")
        
        # Режим отображения и подсветка
        show_raw = request.args.get('raw', '0') == '1'
        q = request.args.get('q') or ''
        
        # Если не передан параметр q, пытаемся взять термины из последнего поиска
        if not q:
            try:
                files_state = _get_files_state()
                last_terms = files_state.get_last_search_terms()
                if last_terms:
                    q = last_terms
            except Exception:
                pass  # Игнорируем ошибки чтения
        
        terms = [t.strip() for t in q.split(',') if t and t.strip()]

        if show_raw:
            base_text = '\n'.join(metadata) + '\n' + content
        else:
            # Фильтруем служебные строки
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                if line.startswith('═') or \
                   line.startswith('[ГРУППА:') or \
                   line.startswith('<!--') or \
                   ('Файлов:' in line and 'Статус:' in line):
                    continue
                filtered_lines.append(line)
            base_text = '\n'.join(metadata) + '\n' + '\n'.join(filtered_lines)

        # Если нет терминов — отдаём как text/plain
        if not terms:
            return Response(base_text, mimetype='text/plain; charset=utf-8')

        # Подсветка: экранируем HTML, затем выделяем совпадения <mark>
        safe = htmllib.escape(base_text)
        highlighted = safe
        for term in terms:
            if not term:
                continue
            try:
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                highlighted = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", highlighted)
            except re.error:
                # Игнорируем некорректный паттерн
                continue

        # Формируем параметры для кнопки переключения режима
        q_param = f"&q={htmllib.escape(q)}" if q else ""
        toggle_text = "Показать с подсветкой" if show_raw else "Показать полную структуру"
        toggle_raw = '0' if show_raw else '1'
        
        html_page = (
            "<!DOCTYPE html>\n"
            "<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<title>Сводный индекс — подсветка</title>\n"
            "<style>body{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;padding:16px;}"
            "pre{white-space:pre-wrap;word-wrap:break-word;background:#f8f8f8;padding:12px;border-radius:6px;}"
            "mark{background:#ffeb3b;padding:0 2px;border-radius:2px;}"
            "a.btn{display:inline-block;margin-bottom:12px;text-decoration:none;background:#3498db;color:#fff;padding:6px 10px;border-radius:4px;margin-right:8px;}"
            ".search-info{background:#e8f5e9;padding:8px 12px;border-radius:4px;margin-bottom:12px;display:inline-block;}"
            "</style>\n"
            "</head><body>\n"
            f"<div><a class=\"btn\" href=\"/\">← На главную</a>"
            f"<a class=\"btn\" href=\"/view_index?raw={toggle_raw}{q_param}\">{toggle_text}</a></div>"
            f"<div class=\"search-info\">🔍 Подсвечены термины: <strong>{', '.join(terms)}</strong></div>"
            "<pre>" + highlighted + "</pre>\n"
            "</body></html>\n"
        )
        return Response(html_page, mimetype='text/html; charset=utf-8')
    
    except Exception as e:
        current_app.logger.exception('Ошибка чтения сводного файла индекса')
        return jsonify({'error': str(e)}), 500


@search_bp.route('/clear_results', methods=['POST'])
def clear_results():
    """Очистка результатов поиска."""
    try:
        files_state = _get_files_state()
        files_state.clear()
        current_app.logger.info('Результаты поиска очищены')
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('Ошибка очистки результатов')
        return jsonify({'error': str(e)}), 500
