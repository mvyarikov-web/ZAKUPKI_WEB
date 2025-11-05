"""Blueprint для работы с файлами (upload, delete, download)."""
import os
import shutil
from flask import Blueprint, request, jsonify, current_app, send_file, Response, g
from urllib.parse import unquote, quote as url_quote
from webapp.services.files import is_safe_subpath, safe_filename, allowed_file
from webapp.services.state import FilesState
from webapp.services.db_indexing import calculate_file_hash, handle_duplicate_upload
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config

files_bp = Blueprint('files', __name__)


def _get_db() -> RAGDatabase:
    """Получить подключение к БД (кешируется в g)."""
    if 'db' not in g:
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        g.db = RAGDatabase(dsn)
    return g.db


def _get_current_user_id() -> int:
    """Получить ID текущего пользователя (заглушка для разработки)."""
    return g.get('user_id', 1)


def _get_files_state():
    """Получить экземпляр FilesState для текущего приложения."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@files_bp.route('/upload', methods=['POST'])
def upload_files():
    """Обработка загрузки файлов"""
    if 'files' not in request.files:
        return jsonify({'error': 'Файлы не выбраны'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    files_state = _get_files_state()
    
    for file in files:
        if file and file.filename != '':
            original_filename = file.filename
            current_app.logger.info(f"Загружается файл: {original_filename}")
            # Пропускаем временные файлы Office (например, ~$file.docx)
            base_name = os.path.basename(original_filename)
            if base_name.startswith('~$') or base_name.startswith('$'):
                current_app.logger.info(f"Пропуск временного файла Office: {original_filename}")
                continue
            
            if allowed_file(original_filename, current_app.config['ALLOWED_EXTENSIONS']):
                # Обрабатываем путь из webkitRelativePath если есть (для папок)
                relative_path = request.form.get('webkitRelativePath', '')
                if not relative_path:
                    # Пытаемся получить путь из самого файла (если поддерживается браузером)
                    relative_path = getattr(file, 'filename', original_filename)
                
                # Разделяем путь на папки и имя файла
                path_parts = relative_path.split('/') if '/' in relative_path else [relative_path]
                filename = path_parts[-1]  # Последняя часть - имя файла
                folder_parts = path_parts[:-1]  # Все предыдущие части - путь к папке
                
                # Создаем безопасные имена для папок и файла, сохраняя кириллицу
                safe_folder_parts = [safe_filename(part) for part in folder_parts if part]
                safe_filename_result = safe_filename(filename)
                
                # Восстанавливаем расширение если safe_filename его удалил
                if '.' not in safe_filename_result and '.' in filename:
                    extension = filename.rsplit('.', 1)[1].lower()
                    safe_filename_result = safe_filename_result + '.' + extension
                
                # Создаем полный путь к папке
                if safe_folder_parts:
                    target_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], *safe_folder_parts)
                    os.makedirs(target_folder, exist_ok=True)
                else:
                    target_folder = current_app.config['UPLOAD_FOLDER']
                
                # Проверяем уникальность имени файла
                counter = 1
                base_name, extension = os.path.splitext(safe_filename_result) if '.' in safe_filename_result else (safe_filename_result, '')
                final_filename = safe_filename_result
                
                while os.path.exists(os.path.join(target_folder, final_filename)):
                    final_filename = f"{base_name}_{counter}{extension}"
                    counter += 1
                
                # Сохраняем файл
                file_path = os.path.join(target_folder, final_filename)
                file.save(file_path)
                
                # Устанавливаем статус "не проверено" для новых файлов
                # Используем относительный путь как ключ для уникальности
                file_key = os.path.join(*safe_folder_parts, final_filename) if safe_folder_parts else final_filename
                files_state.set_file_status(file_key, 'not_checked', 
                                          {'original_name': filename})
                
                # Дедупликация и индексация в БД (если не отключено)
                config = get_config()
                if not config.uploads_disabled:
                    try:
                        db = _get_db()
                        owner_id = _get_current_user_id()
                        sha256_hash = calculate_file_hash(file_path)
                        
                        if sha256_hash:
                            doc_id, message, is_duplicate = handle_duplicate_upload(
                                db, owner_id, file_path, sha256_hash,
                                config.chunk_size_tokens, config.chunk_overlap_tokens
                            )
                            
                            # Добавляем информацию о дедупликации в статус файла
                            if is_duplicate:
                                files_state.set_file_status(file_key, 'indexed_duplicate', {
                                    'original_name': filename,
                                    'message': message,
                                    'document_id': doc_id
                                })
                            else:
                                files_state.set_file_status(file_key, 'indexed', {
                                    'original_name': filename,
                                    'document_id': doc_id
                                })
                            
                            current_app.logger.info(f"Файл проиндексирован: {file_path} → doc#{doc_id}, {message}")
                    except Exception:
                        current_app.logger.exception(f'Ошибка дедупликации/индексации при загрузке: {file_path}')
                        # Не блокируем загрузку при ошибке индексации
                
                uploaded_files.append(final_filename)
                current_app.logger.info(f"Файл сохранён: {file_path}, ключ: {file_key}")
            else:
                return jsonify({'error': f'Неподдерживаемый тип файла: {original_filename}'}), 400
    
    current_app.logger.info(f"Загружено файлов: {len(uploaded_files)}")
    return jsonify({'success': True, 'uploaded_files': uploaded_files})


@files_bp.route('/delete/<path:filepath>', methods=['DELETE'])
def delete_file(filepath):
    """Удаление файла"""
    try:
        decoded_filepath = unquote(filepath)
        current_app.logger.info(f"Попытка удалить файл: {decoded_filepath}")
        
        # Проверяем, что это не попытка выйти за пределы папки uploads
        if not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_filepath):
            return jsonify({'error': 'Недопустимый путь к файлу'}), 400
        
        # Полный путь к файлу
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], decoded_filepath)
        current_app.logger.debug(f"Полный путь к файлу: {file_path}")
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            
            # Удаляем из статусов файлов
            files_state = _get_files_state()
            all_statuses = files_state.get_file_status()
            # Удаляем все возможные варианты ключей
            all_statuses.pop(decoded_filepath, None)
            all_statuses.pop(os.path.basename(decoded_filepath), None)
            files_state.update_file_statuses(all_statuses)
            
            current_app.logger.info(f"Файл {decoded_filepath} успешно удалён")
            return jsonify({'success': True})
        else:
            current_app.logger.warning(f"Файл не найден: {file_path}")
            return jsonify({'error': 'Файл не найден'}), 404
            
    except Exception as e:
        current_app.logger.exception(f"Ошибка при удалении файла: {str(e)}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/delete_folder/<path:folder_path>', methods=['DELETE'])
def delete_folder(folder_path):
    """Удаление папки со всеми файлами"""
    try:
        decoded_folder_path = unquote(folder_path)
        current_app.logger.info(f"Попытка удалить папку: {decoded_folder_path}")
        
        # Проверяем безопасность пути
        if decoded_folder_path != 'root' and not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_folder_path):
            return jsonify({'error': 'Недопустимый путь к папке'}), 400
        
        files_state = _get_files_state()
        all_statuses = files_state.get_file_status()
        
        if decoded_folder_path == 'root':
            # Удаление всех файлов из корневой папки uploads
            target_folder = current_app.config['UPLOAD_FOLDER']
            deleted_files = []
            
            if os.path.exists(target_folder):
                for item in os.listdir(target_folder):
                    item_path = os.path.join(target_folder, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_files.append(item)
                        # Удаляем из статусов
                        all_statuses.pop(item, None)
                        
            message = f'Удалено {len(deleted_files)} файлов из корневой папки'
        else:
            # Удаление подпапки
            target_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], decoded_folder_path)
            
            if not os.path.exists(target_folder):
                return jsonify({'error': 'Папка не найдена'}), 404
            
            # Собираем список файлов для удаления из статусов
            files_to_remove_from_status = []
            for root, dirs, files in os.walk(target_folder):
                for filename in files:
                    rel_path = os.path.relpath(os.path.join(root, filename), current_app.config['UPLOAD_FOLDER'])
                    files_to_remove_from_status.append(rel_path)
            
            # Удаляем папку рекурсивно
            shutil.rmtree(target_folder)
            
            # Удаляем файлы из статусов
            for file_key in files_to_remove_from_status:
                all_statuses.pop(file_key, None)
                all_statuses.pop(os.path.basename(file_key), None)
            
            message = f'Папка "{decoded_folder_path}" успешно удалена'
        
        # Сохраняем обновленные результаты
        files_state.update_file_statuses(all_statuses)
        current_app.logger.info(message)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        current_app.logger.exception(f"Ошибка при удалении папки: {str(e)}")
        return jsonify({'error': f'Ошибка удаления папки: {str(e)}'}), 500


@files_bp.get('/download/<path:filepath>')
def download_file(filepath: str):
    """Безопасная выдача файла из uploads."""
    try:
        decoded_filepath = unquote(filepath)
        
        # Обычный файл
        if not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_filepath):
            return jsonify({'error': 'Недопустимый путь'}), 400
        
        full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], decoded_filepath)
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'error': 'Файл не найден'}), 404
        
        fname = os.path.basename(decoded_filepath)
        ext = os.path.splitext(fname)[1].lower().lstrip('.')
        
        # Блокируем скачивание неподдерживаемых форматов (кроме PREVIEW_INLINE_EXTENSIONS)
        if not allowed_file(decoded_filepath, current_app.config['ALLOWED_EXTENSIONS']) and ext not in current_app.config.get('PREVIEW_INLINE_EXTENSIONS', set()):
            return jsonify({'error': 'Неподдерживаемый тип файла'}), 403
        
        # Блокируем файлы с проблемами (unsupported/error/char_count==0)
        files_state = _get_files_state()
        meta = files_state.get_file_status(decoded_filepath)
        if not meta:
            # Попробуем найти по basename
            meta = files_state.get_file_status(fname)
        if meta.get('status') in ('unsupported', 'error') or (meta.get('char_count') == 0):
            return jsonify({'error': 'Файл недоступен для скачивания'}), 403
        
        # Определяем, можно ли отображать inline
        inline = ext in current_app.config.get('PREVIEW_INLINE_EXTENSIONS', set())
        
        # Range support для больших файлов
        range_header = request.headers.get('Range')
        file_size = os.path.getsize(full_path)
        
        if range_header:
            import re
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                
                with open(full_path, 'rb') as f:
                    f.seek(start)
                    data = f.read(length)
                
                resp = Response(data, 206, mimetype='application/octet-stream')
                resp.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                resp.headers['Accept-Ranges'] = 'bytes'
                resp.headers['Content-Length'] = str(length)
                return resp
        
        # Обычная отдача файла
        resp = send_file(full_path, as_attachment=not inline, download_name=fname)
        
        # Устанавливаем правильный Content-Disposition с UTF-8
        dl = not inline
        try:
            disp = 'attachment' if dl else 'inline'
            fname_enc = url_quote(fname, safe='')
            resp.headers['Content-Disposition'] = f"{disp}; filename=\"{fname}\"; filename*=UTF-8''{fname_enc}"
        except Exception:
            try:
                resp.headers['Content-Disposition'] = f'{disp}; filename="{fname}"'
            except Exception:
                pass
        
        return resp
    
    except Exception as e:
        current_app.logger.exception('download_file error')
        return jsonify({'error': str(e)}), 500


@files_bp.route('/clear_all', methods=['POST'])
def clear_all():
    """Очистка всех загруженных файлов и индекса (increment-002)."""
    try:
        uploads = current_app.config['UPLOAD_FOLDER']
        index_folder = current_app.config['INDEX_FOLDER']
        
        deleted_files_count = 0
        index_deleted = False
        errors = []
        
        # Удаляем все файлы и папки из uploads/
        if os.path.exists(uploads):
            for item in os.listdir(uploads):
                item_path = os.path.join(uploads, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_files_count += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        deleted_files_count += 1
                except Exception as e:
                    current_app.logger.warning(f"Не удалось удалить {item_path}: {e}")
                    errors.append({'path': item, 'error': str(e)})
        
        # Удаляем индексный файл
        index_path = os.path.join(index_folder, '_search_index.txt')
        if os.path.exists(index_path):
            try:
                os.remove(index_path)
                index_deleted = True
            except Exception as e:
                current_app.logger.warning(f"Не удалось удалить индекс: {e}")
                errors.append({'path': '_search_index.txt', 'error': str(e)})
        
        # Очищаем файл с результатами поиска
        results_file = current_app.config['SEARCH_RESULTS_FILE']
        if os.path.exists(results_file):
            try:
                os.remove(results_file)
            except Exception as e:
                current_app.logger.warning(f"Не удалось удалить результаты поиска: {e}")
                errors.append({'path': 'search_results.json', 'error': str(e)})
        
        # Очищаем состояние в памяти
        files_state = _get_files_state()
        files_state.clear()
        
        current_app.logger.info(f"Очистка завершена: удалено элементов={deleted_files_count}, индекс={index_deleted}, ошибок={len(errors)}")
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_files_count,
            'index_deleted': index_deleted,
            'errors': errors
        })
        
    except Exception as e:
        current_app.logger.exception('Ошибка при полной очистке')
        return jsonify({'success': False, 'error': str(e)}), 200


def _build_tree_recursive(base_path: str, current_path: str, allowed_extensions: set, all_statuses: dict) -> tuple:
    """
    Рекурсивно строит дерево файлов и папок.
    
    Args:
        base_path: Корневой путь (uploads/)
        current_path: Текущая обрабатываемая папка
        allowed_extensions: Набор поддерживаемых расширений
        all_statuses: Словарь статусов файлов
    
    Returns:
        tuple: (tree_structure, file_count)
            tree_structure: {'folders': {}, 'files': []}
            file_count: количество файлов
    """
    tree = {'folders': {}, 'files': []}
    file_count = 0
    
    try:
        items = os.listdir(current_path)
    except (OSError, PermissionError):
        return tree, 0
    
    for item in items:
        # Пропускаем служебные файлы
        if item == '_search_index.txt' or item.startswith('~$') or item.startswith('$'):
            continue
        
        item_path = os.path.join(current_path, item)
        rel_path = os.path.relpath(item_path, base_path)
        
        if os.path.isdir(item_path):
            # Рекурсивно обрабатываем подпапку
            subtree, subcount = _build_tree_recursive(base_path, item_path, allowed_extensions, all_statuses)
            tree['folders'][item] = subtree
            file_count += subcount
        else:
            # Это файл
            file_info = {
                'name': item,
                'path': rel_path,
                'size': os.path.getsize(item_path),
            }
            
            # Проверяем поддержку формата
            if not allowed_file(item, allowed_extensions):
                file_info['unsupported'] = True
                if rel_path not in all_statuses:
                    all_statuses[rel_path] = {
                        'status': 'unsupported',
                        'char_count': 0,
                        'error': 'Неподдерживаемый формат'
                    }
            
            tree['files'].append(file_info)
            file_count += 1
    
    return tree, file_count


@files_bp.get('/files_json')
def files_json():
    """JSON-дерево файлов в uploads с поддержкой вложенных подпапок."""
    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        return jsonify({'tree': {'folders': {}, 'files': []}, 'total_files': 0, 'file_statuses': {}})
    
    # Получаем статусы всех файлов
    files_state = _get_files_state()
    all_statuses = files_state.get_file_status()
    
    # Строим рекурсивное дерево
    tree, total_files = _build_tree_recursive(
        uploads,
        uploads,
        current_app.config['ALLOWED_EXTENSIONS'],
        all_statuses
    )
    
    return jsonify({
        'tree': tree,
        'total_files': total_files,
        'file_statuses': all_statuses
    })


# Для обратной совместимости: старый формат (плоский)
@files_bp.get('/files_json_legacy')
def files_json_legacy():
    """JSON-список файлов в uploads (старый формат без вложенных подпапок)."""
    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        return jsonify({'folders': {}, 'total_files': 0, 'file_statuses': {}})
    
    files_by_folder = {}
    total_files = 0
    
    # Получаем статусы всех файлов
    files_state = _get_files_state()
    all_statuses = files_state.get_file_status()
    
    # Обходим только 1 уровень вложенности
    for item in os.listdir(uploads):
        item_path = os.path.join(uploads, item)
        
        # Скрываем служебные файлы
        if item == '_search_index.txt' or item.startswith('~$') or item.startswith('$'):
            continue
        
        if os.path.isdir(item_path):
            # Это папка - показываем её содержимое
            folder_key = item
            if folder_key not in files_by_folder:
                files_by_folder[folder_key] = []
            
            # Обрабатываем файлы внутри папки (без вложенных подпапок)
            for subitem in os.listdir(item_path):
                subitem_path = os.path.join(item_path, subitem)
                
                # Пропускаем служебные файлы
                if subitem.startswith('~$') or subitem.startswith('$') or subitem == '_search_index.txt':
                    continue
                
                # Пропускаем вложенные подпапки (по спецификации 000)
                if os.path.isdir(subitem_path):
                    continue
                
                # Формируем относительный путь
                rel_path = os.path.join(item, subitem)
                
                # Проверяем поддержку формата
                if not allowed_file(subitem, current_app.config['ALLOWED_EXTENSIONS']):
                    # Неподдерживаемый файл
                    file_info = {
                        'name': subitem,
                        'path': rel_path,
                        'size': os.path.getsize(subitem_path),
                    }
                    files_by_folder[folder_key].append(file_info)
                    
                    # Устанавливаем статус unsupported
                    if rel_path not in all_statuses:
                        all_statuses[rel_path] = {
                            'status': 'unsupported',
                            'char_count': 0,
                            'error': 'Неподдерживаемый формат'
                        }
                    total_files += 1
                    continue
                
                # Поддерживаемый файл
                file_info = {
                    'name': subitem,
                    'path': rel_path,
                    'size': os.path.getsize(subitem_path),
                }
                files_by_folder[folder_key].append(file_info)
                total_files += 1
        
        else:
            # Файл в корне uploads
            # Проверяем поддержку формата
            if not allowed_file(item, current_app.config['ALLOWED_EXTENSIONS']):
                folder_key = 'root'
                if folder_key not in files_by_folder:
                    files_by_folder[folder_key] = []
                
                file_info = {
                    'name': item,
                    'path': item,
                    'size': os.path.getsize(item_path),
                }
                files_by_folder[folder_key].append(file_info)
                
                if item not in all_statuses:
                    all_statuses[item] = {
                        'status': 'unsupported',
                        'char_count': 0,
                        'error': 'Неподдерживаемый формат'
                    }
                total_files += 1
                continue
            
            folder_key = 'root'
            if folder_key not in files_by_folder:
                files_by_folder[folder_key] = []
            
            file_info = {
                'name': item,
                'path': item,
                'size': os.path.getsize(item_path),
            }
            files_by_folder[folder_key].append(file_info)
            total_files += 1
    
    return jsonify({
        'folders': files_by_folder,
        'total_files': total_files,
        'file_statuses': all_statuses
    })
