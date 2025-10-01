"""Blueprint для страниц (index, view)."""
import os
from flask import Blueprint, render_template, jsonify, request, current_app
from markupsafe import Markup
from webapp.services.files import allowed_file
from webapp.services.state import FilesState
from webapp.services.indexing import get_index_path

pages_bp = Blueprint('pages', __name__)


def _get_files_state():
    """Получить экземпляр FilesState для текущего приложения."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@pages_bp.route('/')
def index():
    """Главная страница"""
    # Загружаем сохраненные результаты поиска
    files_state = _get_files_state()
    last_search_terms = files_state.get_last_search_terms()
    file_status = files_state.get_file_status()
    
    # Получаем список загруженных файлов с группировкой по папкам
    files_by_folder = {}
    total_files = 0
    
    current_app.logger.info(f"Проверяем папку: {current_app.config['UPLOAD_FOLDER']}")
    
    if os.path.exists(current_app.config['UPLOAD_FOLDER']):
        # Рекурсивно обходим все файлы и папки
        for root, dirs, files in os.walk(current_app.config['UPLOAD_FOLDER']):
            for filename in files:
                # Скрываем служебный индексный файл и временные файлы Office
                if filename == '_search_index.txt' or filename.startswith('~$') or filename.startswith('$'):
                    continue
                file_path = os.path.join(root, filename)
                # Определяем относительную папку
                relative_folder = os.path.relpath(root, current_app.config['UPLOAD_FOLDER'])

                # Правильно определяем название папки
                if relative_folder == '.':
                    folder_display_name = '📁 Загруженные файлы'
                    folder_key = 'root'
                else:
                    folder_parts = relative_folder.split(os.sep)
                    original_folder_name = folder_parts[-1]
                    folder_display_name = f'📂 {original_folder_name}'
                    folder_key = relative_folder

                file_size = os.path.getsize(file_path)
                file_key = os.path.join(relative_folder, filename) if relative_folder != '.' else filename
                file_data = file_status.get(file_key, {})
                status = file_data.get('status', 'not_checked')
                # Если формат не поддерживается — пометим явно
                if not allowed_file(filename, current_app.config['ALLOWED_EXTENSIONS']):
                    status = 'unsupported'
                    file_data = {**file_data, 'status': 'unsupported', 'error': 'Неподдерживаемый формат'}
                    files_state.set_file_status(file_key, 'unsupported', 
                                               {'error': 'Неподдерживаемый формат'})

                display_name = file_data.get('original_name', filename)
                file_info = {
                    'name': display_name,
                    'size': file_size,
                    'status': status,
                    'path': file_key,
                    'relative_folder': relative_folder
                }

                if folder_key not in files_by_folder:
                    files_by_folder[folder_key] = {
                        'display_name': folder_display_name,
                        'relative_path': relative_folder,
                        'files': []
                    }

                files_by_folder[folder_key]['files'].append(file_info)
                total_files += 1
                current_app.logger.debug(f"Добавлен файл: {filename} в папку {folder_display_name}, размер: {file_size}, статус: {status}")
    else:
        current_app.logger.warning("Папка uploads не существует")
    
    current_app.logger.info(f"Всего файлов для отображения: {total_files}, папок: {len(files_by_folder)}")
    return render_template(
        'index.html',
        files_by_folder=files_by_folder,
        total_files=total_files,
        last_search_terms=last_search_terms,
        file_status=file_status,
    )


@pages_bp.get('/view/<path:filepath>')
def view_file(filepath: str):
    """Отображение содержимого файла с подсветкой ключевых слов.
    
    FR-003: Читает текст из сводного индекса (_search_index.txt) вместо оригинального файла.
    """
    from urllib.parse import unquote
    from webapp.services.files import is_safe_subpath
    
    try:
        decoded_filepath = unquote(filepath)
        current_app.logger.info(f"Просмотр файла из индекса: {decoded_filepath}")
        
        # Проверка безопасности пути
        if not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_filepath):
            return jsonify({'error': 'Недопустимый путь к файлу'}), 400
        
        # Проверяем статус файла
        files_state = _get_files_state()
        file_data = files_state.get_file_status(decoded_filepath)
        
        status = file_data.get('status', 'not_checked')
        char_count = file_data.get('char_count')
        error = file_data.get('error')
        
        # FR-001, FR-002: Запрещаем чтение неподдерживаемых, ошибочных и пустых файлов
        # Возвращаем понятное сообщение вместо JSON
        if status == 'unsupported':
            return render_template('view.html',
                                 title=os.path.basename(decoded_filepath),
                                 content=Markup('<div class="error-message">Просмотр файла не поддерживается</div>'),
                                 keywords=[])
        if status == 'error' or error:
            return render_template('view.html',
                                 title=os.path.basename(decoded_filepath),
                                 content=Markup('<div class="error-message">Просмотр файла не поддерживается</div>'),
                                 keywords=[])
        if char_count == 0:
            return render_template('view.html',
                                 title=os.path.basename(decoded_filepath),
                                 content=Markup('<div class="error-message">Просмотр файла не поддерживается</div>'),
                                 keywords=[])
        
        # FR-003: Читаем текст из индекса
        index_path = get_index_path(current_app.config['INDEX_FOLDER'])
        if not os.path.exists(index_path):
            return jsonify({'error': 'Индекс не создан. Постройте индекс перед просмотром.'}), 404
        
        text = _extract_text_from_index(index_path, decoded_filepath)
        
        if not text:
            # Возвращаем HTML-превью с сообщением об ошибке
            return render_template('view.html',
                                 filename=os.path.basename(decoded_filepath),
                                 content=Markup('<div class="error-message">Не удалось извлечь текст из индекса</div>'),
                                 keywords=[])
        
        # Получаем ключевые слова из query параметра
        query = request.args.get('q', '')
        keywords = [k.strip() for k in query.split(',') if k.strip()] if query else []
        
        # Подсветка ключевых слов
        if keywords:
            import re
            for keyword in keywords:
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                text = pattern.sub(lambda m: f'<mark>{m.group(0)}</mark>', text)
        
        # Экранируем HTML для безопасности (кроме наших mark)
        # text уже содержит <mark>, поэтому используем Markup
        safe_text = Markup(text.replace('<', '&lt;').replace('>', '&gt;')
                          .replace('&lt;mark&gt;', '<mark>')
                          .replace('&lt;/mark&gt;', '</mark>'))
        
        return render_template('view.html',
                             filename=os.path.basename(decoded_filepath),
                             content=safe_text,
                             keywords=keywords)
    
    except Exception as e:
        current_app.logger.exception('view_file error')
        return jsonify({'error': str(e)}), 500


def _extract_text_from_index(index_path: str, target_path: str) -> str:
    """Извлекает текст из индекса для указанного файла, используя маркеры начала и конца.
    
    FR-003: Источник данных для окна просмотра — индекс, без повторного чтения исходных файлов.
    
    Args:
        index_path: Путь к файлу индекса
        target_path: Относительный путь к целевому файлу
        
    Returns:
        Извлечённый текст или пустая строка
    """
    import re
    import os
    
    # Маркеры для поиска содержимого документа
    DOC_START_MARKER = "<<< НАЧАЛО ДОКУМЕНТА >>>"
    DOC_END_MARKER = "<<< КОНЕЦ ДОКУМЕНТА >>>"
    
    try:
        # Нормализуем путь для поиска
        norm_target = target_path.replace('\\', '/')
        norm_target_clean = re.sub(r'^(zip://|rar://)', '', norm_target)
        
        current_app.logger.debug(f"Поиск в индексе с маркерами: target_path='{target_path}', norm_target='{norm_target}', norm_target_clean='{norm_target_clean}'")
        
        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Ищем заголовок документа
        patterns = [
            rf"ЗАГОЛОВОК: {re.escape(norm_target)}\n",
            rf"ЗАГОЛОВОК: {re.escape(norm_target_clean)}\n",
            rf"ЗАГОЛОВОК: .*{re.escape(os.path.basename(norm_target))}\n",
            rf"ЗАГОЛОВОК: .*{re.escape(os.path.basename(norm_target_clean))}\n"
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE))
            if matches:
                current_app.logger.debug(f"Найдено {len(matches)} соответствий по шаблону: {pattern}")
                
                for match in matches:
                    # Ищем маркер начала документа после заголовка
                    start_pos = content.find(DOC_START_MARKER, match.end())
                    if start_pos == -1:
                        continue
                    
                    # Ищем маркер конца документа
                    end_pos = content.find(DOC_END_MARKER, start_pos + len(DOC_START_MARKER))
                    if end_pos == -1:
                        # Если маркер конца не найден, берем до конца файла
                        document_text = content[start_pos + len(DOC_START_MARKER):].strip()
                    else:
                        document_text = content[start_pos + len(DOC_START_MARKER):end_pos].strip()
                    
                    if document_text:
                        current_app.logger.debug(f"Извлечен текст ({len(document_text)} символов) для '{target_path}'")
                        return document_text
        
        # Если с маркерами не найдено, пробуем старый способ для совместимости
        current_app.logger.debug(f"Попытка извлечения старым способом для '{target_path}'")
        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_target = False
            text_lines = []
            header_bar = "=" * 31
            for line in f:
                stripped = line.rstrip('\n')
                if stripped == header_bar:
                    if in_target:
                        break
                    in_target = False
                    text_lines = []
                    continue
                if stripped.startswith('ЗАГОЛОВОК:'):
                    title = stripped.split(':', 1)[1].strip().replace('\\', '/')
                    title_clean = re.sub(r'^(zip://|rar://)', '', title)
                    
                    if (title == norm_target or 
                        title_clean == norm_target_clean or
                        title.endswith(norm_target) or 
                        title_clean.endswith(norm_target_clean) or
                        norm_target.endswith(title_clean) or
                        norm_target_clean.endswith(title_clean) or
                        title.endswith('/' + os.path.basename(norm_target)) or
                        title_clean.endswith('/' + os.path.basename(norm_target_clean))):
                        in_target = True
                        current_app.logger.debug(f"Найден блок для '{target_path}' в заголовке '{title}' (старый способ)")
                    continue
                if stripped.startswith('Формат:') or stripped.startswith('Источник:'):
                    continue
                if in_target:
                    text_lines.append(line.rstrip('\n'))
            
            result = '\n'.join(text_lines)
            current_app.logger.debug(f"Извлечено символов (старый способ): {len(result)} для '{target_path}'")
            return result
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка извлечения текста из индекса для {target_path}')
        return ''
    
