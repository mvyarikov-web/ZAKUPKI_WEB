"""Blueprint для поиска и индексации."""
import os
import re
import shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, Response
from document_processor import DocumentProcessor
from document_processor.search.searcher import Searcher
from webapp.services.files import allowed_file
from webapp.services.state import FilesState
from webapp.services.indexing import (
    build_search_index, 
    search_in_index, 
    get_index_path,
    parse_index_char_counts
)

search_bp = Blueprint('search', __name__)


def _get_files_state():
    """Получить экземпляр FilesState для текущего приложения."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


def _search_in_files(search_terms, exclude_mode=False):
    """НОВАЯ логика: поиск по сводному индексу (_search_index.txt), игнорируя заголовки.
    Группирует результаты по файлам и обновляет статусы file_status.
    Параметр exclude_mode: если True, ищет файлы, которые НЕ содержат ключевые слова.
    """
    results = []
    terms = [t.strip() for t in search_terms.split(',') if t.strip()]
    if not terms:
        return results

    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        current_app.logger.warning('Папка uploads не существует при поиске')
        return results

    # Собираем список реальных файлов для отображения статусов
    files_to_search = []
    for root, dirs, files in os.walk(uploads):
        for fname in files:
            # Исключаем служебный индекс и временные Office-файлы
            if fname == '_search_index.txt' or fname.startswith('~$') or fname.startswith('$'):
                continue
            if allowed_file(fname, current_app.config['ALLOWED_EXTENSIONS']):
                rel_path = os.path.relpath(os.path.join(root, fname), uploads)
                files_to_search.append(rel_path)

    # Убедимся, что индекс существует (если нет — создадим)
    index_path = get_index_path(current_app.config['INDEX_FOLDER'])
    if not os.path.exists(index_path):
        try:
            dp = DocumentProcessor()
            tmp_index = dp.create_search_index(uploads)
            # Переместим в папку index
            os.makedirs(current_app.config['INDEX_FOLDER'], exist_ok=True)
            if tmp_index != index_path and os.path.exists(tmp_index):
                shutil.move(tmp_index, index_path)
            current_app.logger.info('Индекс создан автоматически для поиска')
        except Exception as e:
            current_app.logger.exception(f'Ошибка создания индекса: {e}')
            return results

    # Поиск по индексу с привязкой к файлам
    try:
        s = Searcher()
        current_app.logger.info(f"Поиск по индексу: terms={terms}, exclude_mode={exclude_mode}")
        matches = s.search(index_path, terms, context=80, exclude_mode=exclude_mode)
    except Exception as e:
        current_app.logger.exception(f'Ошибка поиска по индексу: {e}')
        matches = []

    # Сгруппируем результаты по файлам и по ключевым словам внутри файла
    grouped: dict[str, dict] = {}
    for m in matches:
        title = m.get('title') or m.get('source') or 'индекс'
        kw = m.get('keyword', '')
        snip = m.get('snippet', '')
        is_exclude = m.get('exclude_mode', False)
        g = grouped.setdefault(title, { 'by_term': {}, 'total': 0, 'exclude_mode': is_exclude })
        tinfo = g['by_term'].setdefault(kw, { 'count': 0, 'snippets': [] })
        tinfo['count'] += 1
        g['total'] += 1
        # В режиме исключения - только 1 сниппет
        max_snippets = 1 if is_exclude else 3
        if len(tinfo['snippets']) < max_snippets and snip:
            tinfo['snippets'].append(snip)

    # Обновим статусы известных файлов и подготовим выдачу
    files_state = _get_files_state()
    # Получаем словарь количеств символов из индекса (реальные и виртуальные пути)
    try:
        counts = parse_index_char_counts(index_path)
    except Exception:
        counts = {}
    found_files = set()
    new_statuses = {}
    
    for rel_path, data in grouped.items():
        # Составим агрегированный список терминов и до 3 сниппетов на термин
        found_terms = []
        context = []
        is_exclude = data.get('exclude_mode', False)
        
        if is_exclude:
            # В режиме исключения добавляем префикс "не содержит" для каждого термина
            for term in terms:
                found_terms.append(f"не содержит: {term}")
            # В режиме исключения только 1 сниппет
            for term, info in data['by_term'].items():
                context.extend(info['snippets'][:1])
        else:
            for term, info in data['by_term'].items():
                if not term:
                    continue
                found_terms.append(f"{term} ({info['count']})")
                context.extend(info['snippets'][:3])
        
        new_entry = {
            'status': 'contains_keywords',
            'found_terms': found_terms,
            'context': context[: max(3, len(context))],
            'processed_at': datetime.now().isoformat()
        }
        
        # Получаем предыдущий статус (для реальных и виртуальных файлов)
        prev = files_state.get_file_status(rel_path)
        # Не затираем ранее сохранённые поля (char_count, error, original_name)
        for k in ('char_count','error','original_name'):
            if k in prev:
                new_entry[k] = prev[k]
        # Обновляем char_count из индекса при наличии
        if isinstance(rel_path, str) and rel_path in counts:
            new_entry['char_count'] = counts[rel_path]
        
        # В режиме обратного поиска: пропускаем непроиндексированные файлы
        # (файлы с char_count == 0 или с ошибками)
        if is_exclude:
            char_count = new_entry.get('char_count', 0)
            if char_count == 0:
                current_app.logger.debug(f"Пропуск непроиндексированного файла в режиме exclude: {rel_path}")
                continue
        
        # Обновляем статус для всех найденных файлов (включая виртуальные из архивов)
        new_statuses[rel_path] = new_entry
        found_files.add(rel_path)
        
        # Добавляем в выдачу
        # Формируем блоки по каждому ключевому слову
        per_term = []
        if is_exclude:
            # В режиме исключения: один блок для всех терминов с префиксом "не содержит"
            all_snippets = []
            for term_data in data['by_term'].values():
                all_snippets.extend(term_data['snippets'][:1])
            
            for original_term in terms:
                per_term.append({
                    'term': f'не содержит: {original_term}',
                    'count': 1,
                    'snippets': all_snippets[:1]  # Только 1 сниппет
                })
        else:
            for term, info in data['by_term'].items():
                per_term.append({
                    'term': term,
                    'count': info['count'],
                    'snippets': info['snippets']
                })
        results.append({
            'filename': os.path.basename(rel_path) if isinstance(rel_path, str) else str(rel_path),
            'source': rel_path,
            'path': rel_path if rel_path in files_to_search else None,
            'total': data['total'],
            'per_term': per_term
        })

    # Реальным файлам без совпадений — статус "нет ключевых слов"
    for rel_path in files_to_search:
        if rel_path not in found_files:
            prev = files_state.get_file_status(rel_path)
            # Проверяем char_count - если 0, то файл не удалось прочитать
            char_count = prev.get('char_count', 0) if isinstance(prev, dict) else 0
            if char_count == 0:
                new_entry = {
                    'status': 'error',
                    'processed_at': datetime.now().isoformat()
                }
            else:
                new_entry = {
                    'status': 'no_keywords',
                    'processed_at': datetime.now().isoformat()
                }
            for k in ('char_count','error','original_name'):
                if k in prev:
                    new_entry[k] = prev[k]
            # Если есть счётчик символов в индексе — сохраним его
            if rel_path in counts:
                new_entry['char_count'] = counts[rel_path]
            new_statuses[rel_path] = new_entry

    # Атомарное обновление всех статусов
    if new_statuses:
        files_state.update_file_statuses(new_statuses)

    current_app.logger.info(f"Поиск завершён: найдено {len(matches)} совпадений, групп: {len(grouped)}")
    return results


@search_bp.route('/search', methods=['POST'])
def search():
    """Поиск по ключевым словам"""
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

    # Новый поиск через индекс
    current_app.logger.info(f"Запрос поиска: terms='{','.join(filtered)}' (из {len(raw_terms)} входных), exclude_mode={exclude_mode}")
    results = _search_in_files(','.join(filtered), exclude_mode=exclude_mode)
    
    # Сохраняем результаты поиска
    files_state = _get_files_state()
    files_state.set_last_search_terms(search_terms)
    
    return jsonify({'results': results})


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
    """Явная сборка индекса по папке uploads."""
    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        return jsonify({'success': False, 'message': 'Папка uploads не найдена'}), 400
    
    # Проверяем, запрошена ли групповая индексация
    use_groups = request.json.get('use_groups', False) if request.is_json else False
    
    try:
        dp = DocumentProcessor()
        current_app.logger.info(f"Запуск явной сборки индекса для uploads (use_groups={use_groups})")
        
        # Создаём индекс в uploads, затем переносим в index/
        tmp_index_path = dp.create_search_index(uploads, use_groups=use_groups)
        os.makedirs(current_app.config['INDEX_FOLDER'], exist_ok=True)
        index_path = get_index_path(current_app.config['INDEX_FOLDER'])
        
        try:
            if os.path.exists(tmp_index_path) and tmp_index_path != index_path:
                shutil.move(tmp_index_path, index_path)
            else:
                # На всякий случай, если реализация уже пишет в index_folder
                if os.path.exists(index_path):
                    pass
        except Exception:
            current_app.logger.exception('Не удалось переместить индекс в папку index')
        
        size = os.path.getsize(index_path) if os.path.exists(index_path) else 0
        current_app.logger.info(f"Индекс собран: {index_path}, размер: {size} байт")
        
        # Обновим количество распознанных символов по каждому файлу (включая виртуальные из архивов) и статусы ошибок/неподдержки
        try:
            counts = parse_index_char_counts(index_path)
            
            # Список всех реальных файлов в uploads
            all_files: list[str] = []
            for root, dirs, files in os.walk(uploads):
                for fname in files:
                    if fname == '_search_index.txt' or fname.startswith('~$') or fname.startswith('$'):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, fname), uploads)
                    all_files.append(rel_path)
            
            files_state = _get_files_state()
            new_statuses = {}
            
            # Обрабатываем реальные файлы
            for rel_path in all_files:
                ext_ok = allowed_file(rel_path, current_app.config['ALLOWED_EXTENSIONS'])
                entry = files_state.get_file_status(rel_path).copy()
                
                if not ext_ok:
                    # Неподдерживаемый формат
                    entry.update({
                        'status': 'unsupported',
                        'error': 'Неподдерживаемый формат',
                        'char_count': 0,
                        'processed_at': datetime.now().isoformat()
                    })
                else:
                    cc = counts.get(rel_path)
                    if cc is None:
                        # Поддерживаемый, но нет записи в индексе — ошибка чтения/индексации
                        entry.update({
                            'status': entry.get('status', 'error' if entry.get('status') in (None, 'not_checked') else entry.get('status')),
                            'error': entry.get('error') or 'Ошибка чтения или не проиндексирован',
                            'char_count': 0,
                            'processed_at': datetime.now().isoformat()
                        })
                    else:
                        # Есть счётчик символов — не трогаем статус поиска, только дополняем метрикой
                        entry.update({
                            'char_count': cc,
                            'processed_at': datetime.now().isoformat()
                        })
                        # если 0 символов, оставим это как индикатор качества (UI подсветит)
                
                new_statuses[rel_path] = entry
            
            # Обрабатываем виртуальные файлы из архивов (те, что есть в индексе, но не в all_files)
            for indexed_path, char_count in counts.items():
                if indexed_path not in all_files and '://' in indexed_path:
                    # Это виртуальный файл из архива
                    entry = files_state.get_file_status(indexed_path).copy()
                    entry.update({
                        'char_count': char_count,
                        'processed_at': datetime.now().isoformat()
                    })
                    # Если статус не установлен, устанавливаем в not_checked
                    if not entry.get('status'):
                        entry['status'] = 'not_checked'
                    new_statuses[indexed_path] = entry
            
            # Атомарно сохраняем все статусы
            files_state.update_file_statuses(new_statuses)
        except Exception:
            current_app.logger.exception('Не удалось обновить char_count по индексу')
        
        return jsonify({'success': True, 'index_path': index_path, 'size': size})
    
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

        idx = get_index_path(current_app.config['INDEX_FOLDER'])
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
        groups_info = _parse_index_groups(idx)
        if groups_info:
            response['groups_info'] = groups_info
        
        # Добавляем информацию о прогрессе если доступна
        if progress_data:
            response['progress'] = progress_data
            # Добавляем статусы из progress_data на верхний уровень
            response['status'] = progress_data.get('status', 'completed')
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
    idx = get_index_path(current_app.config['INDEX_FOLDER'])
    if not os.path.exists(idx):
        return jsonify({'error': 'Индекс не найден'}), 404
    
    try:
        with open(idx, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Добавляем метаинформацию в начало
        metadata = [
            f"# Сводный индекс поиска",
            f"# Размер: {len(content)} байт",
            f"# Обновлён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"#",
            f"# Формат: групповая структура (increment-014)",
            f"# Группы: FAST (TXT,CSV,HTML) → MEDIUM (DOCX,XLSX,PDF) → SLOW (OCR)",
            f"#",
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
        
        # Режим отображения
        show_raw = request.args.get('raw', '0') == '1'
        
        if show_raw:
            # Показываем как есть
            full_content = '\n'.join(metadata) + '\n' + content
        else:
            # Фильтруем служебные строки
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                # Пропускаем заголовки групп и маркеры
                if line.startswith('═') or \
                   line.startswith('[ГРУППА:') or \
                   line.startswith('<!--') or \
                   ('Файлов:' in line and 'Статус:' in line):
                    continue
                filtered_lines.append(line)
            
            full_content = '\n'.join(metadata) + '\n' + '\n'.join(filtered_lines)
        
        return Response(full_content, mimetype='text/plain; charset=utf-8')
    
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
