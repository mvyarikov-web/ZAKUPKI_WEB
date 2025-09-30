"""Blueprint для работы с файлами (upload, delete, download)."""
import os
import shutil
from flask import Blueprint, request, jsonify, current_app, send_file, Response
from urllib.parse import unquote, quote as url_quote
from app.services.files import is_safe_subpath, safe_filename, allowed_file
from app.services.state import FilesState

files_bp = Blueprint('files', __name__)


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
        if not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_filepath):
            return jsonify({'error': 'Недопустимый путь'}), 400
        
        full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], decoded_filepath)
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'error': 'Файл не найден'}), 404
        
        fname = os.path.basename(decoded_filepath)
        ext = os.path.splitext(fname)[1].lower().lstrip('.')
        
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


@files_bp.get('/files_json')
def files_json():
    """JSON-список файлов в uploads, сгруппированный по папкам (упрощённо)."""
    uploads = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(uploads):
        return jsonify({'folders': {}, 'total_files': 0})
    
    files_by_folder = {}
    total_files = 0
    
    for root, dirs, files in os.walk(uploads):
        rel_dir = os.path.relpath(root, uploads)
        for filename in files:
            # Скрываем служебный индексный файл и временные файлы Office
            if filename == '_search_index.txt' or filename.startswith('~$') or filename.startswith('$'):
                continue
            if not allowed_file(filename, current_app.config['ALLOWED_EXTENSIONS']):
                continue
            
            file_path = os.path.join(root, filename)
            rel_path = os.path.normpath(os.path.join(rel_dir, filename)) if rel_dir != '.' else filename
            folder_key = 'root' if rel_dir == '.' else rel_dir
            
            if folder_key not in files_by_folder:
                files_by_folder[folder_key] = []
            
            files_by_folder[folder_key].append({
                'name': filename,
                'path': rel_path,
                'size': os.path.getsize(file_path)
            })
            total_files += 1
    
    return jsonify({'folders': files_by_folder, 'total_files': total_files})
