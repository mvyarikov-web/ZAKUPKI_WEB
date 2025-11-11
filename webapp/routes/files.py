"""Blueprint для работы с файлами (upload, delete, download)."""
import os
import shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file, Response, g
from urllib.parse import unquote, quote as url_quote
from webapp.services.files import is_safe_subpath, safe_filename, allowed_file
from webapp.services.file_search_state_service import FileSearchStateService
# Legacy imports removed: calculate_file_hash, handle_duplicate_upload (Блок 10)
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config
from webapp.utils.path_utils import normalize_path, get_relative_path
from webapp.db.base import SessionLocal

files_bp = Blueprint('files', __name__)


def _get_rag_db() -> RAGDatabase:
    """Получить RAGDatabase (psycopg2) для legacy-операций (кешируется в g)."""
    if 'rag_db' not in g:
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        g.rag_db = RAGDatabase(dsn)
    return g.rag_db


def _get_db():
    """Получить SQLAlchemy сессию для query() операций (кешируется в g)."""
    if 'db_session' not in g:
        g.db_session = SessionLocal()
    return g.db_session


def required_user_id() -> int:
    """Строго получить user_id.

    Поведение:
    - Если STRICT_USER_ID=true: требуем явный X-User-ID или g.user.id, иначе 400.
    - Если STRICT_USER_ID=false: пытаемся взять g.user.id, затем X-User-ID, затем fallback=1.
    Возвращает целочисленный user_id при успехе.
    """
    config = get_config()
    strict = config.strict_user_id

    # 1) g.user.id если присутствует
    try:
        user = getattr(g, 'user', None)
        if user and getattr(user, 'id', None):
            return int(user.id)
    except Exception:
        pass

    # 2) Заголовок X-User-ID
    try:
        uid = request.headers.get('X-User-ID')
        if uid and str(uid).isdigit():
            return int(uid)
    except Exception:
        pass

    # 3) Строгий режим: ошибка
    if strict:
        raise ValueError('user_id отсутствует (STRICT_USER_ID)')

    # 4) Нестрогий режим: fallback
    return 1


def _get_files_state():
    """Получить экземпляр FileSearchStateService для текущего приложения."""
    # Сервис сам определит путь к файлу из конфига
    return FileSearchStateService()


@files_bp.route('/upload', methods=['POST'])
def upload_files():
    """
    Обработка загрузки файлов (ИНКРЕМЕНТ 020 - Блок 9).
    
    НОВАЯ АРХИТЕКТУРА:
    - Файлы сохраняются в documents.blob (PostgreSQL)
    - НЕ создаются физические файлы в uploads/
    - Автоматическая дедупликация по SHA256
    - Автоматическая индексация из blob
    - Автоматический prune при превышении лимита БД
    """
    if 'files' not in request.files:
        return jsonify({'error': 'Файлы не выбраны'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    
    # Получаем user_id
    try:
        user_id = required_user_id()
    except ValueError:
        current_app.logger.warning('Загрузка отклонена: отсутствует user_id при STRICT_USER_ID')
        return jsonify({'error': 'Не указан идентификатор пользователя (X-User-ID)'}), 400
    
    # Инициализируем сервисы
    config = get_config()
    db = _get_db()
    from webapp.services.blob_storage_service import BlobStorageService
    blob_service = BlobStorageService(config)
    
    for file in files:
        if file and file.filename != '':
            original_filename = file.filename
            current_app.logger.info(f"Загружается файл: {original_filename}")
            
            # Пропускаем временные файлы Office (например, ~$file.docx)
            base_name = os.path.basename(original_filename)
            if base_name.startswith('~$') or base_name.startswith('$'):
                current_app.logger.info(f"Пропуск временного файла Office: {original_filename}")
                continue
            
            if not allowed_file(original_filename, current_app.config['ALLOWED_EXTENSIONS']):
                return jsonify({'error': f'Неподдерживаемый тип файла: {original_filename}'}), 400
            
            # Обрабатываем путь из webkitRelativePath если есть (для папок)
            relative_path = request.form.get('webkitRelativePath', '')
            if not relative_path:
                relative_path = original_filename
            
            # Формируем безопасный user_path (для хранения структуры папок в БД)
            path_parts = relative_path.split('/') if '/' in relative_path else [relative_path]
            safe_parts = [safe_filename(part) for part in path_parts if part]
            user_path = '/'.join(safe_parts) if safe_parts else original_filename
            
            try:
                # ✨ НОВЫЙ ПУТЬ: сохранение в blob через BlobStorageService
                document, is_new = blob_service.save_file_to_db(
                    db=db,
                    file=file,
                    user_id=user_id,
                    user_path=user_path,
                    mime_type=file.content_type
                )
                
                # Автоматическая индексация из blob (если документ новый)
                if is_new:
                    from webapp.services.db_indexing import index_document_to_db
                    config = get_config()
                    rag_db = _get_rag_db()  # RAGDatabase для index_document_to_db
                    
                    try:
                        file_info = {
                            'sha256': document.sha256,
                            'size': document.size_bytes,
                            'content_type': document.mime or 'application/octet-stream'
                        }
                        
                        doc_id, indexing_cost = index_document_to_db(
                            db=rag_db,
                            file_path="",  # Пустой путь - индексация из blob
                            file_info=file_info,
                            user_id=user_id,
                            original_filename=safe_parts[-1],  # Последняя часть user_path - имя файла
                            user_path=user_path,
                            chunk_size_tokens=config.chunk_size_tokens,
                            chunk_overlap_tokens=config.chunk_overlap_tokens
                        )
                        current_app.logger.info(
                            f"✅ Файл загружен и проиндексирован: {user_path} → doc#{doc_id} (новый, {indexing_cost:.3f}s)"
                        )
                    except Exception as e:
                        current_app.logger.exception(f"Ошибка индексации doc#{document.id}: {e}")
                        # Документ сохранён в blob, но индексация не удалась
                        # Можно повторить позже через /build_index
                else:
                    current_app.logger.info(
                        f"✅ Файл загружен (дедупликация): {user_path} → doc#{document.id} (существующий)"
                    )
                
                uploaded_files.append({
                    'filename': original_filename,
                    'user_path': user_path,
                    'document_id': document.id,
                    'is_new': is_new,
                    'size_bytes': document.size_bytes
                })
                
            except RuntimeError as e:
                # Ошибка при prune или превышение лимита
                current_app.logger.error(f"Ошибка загрузки {user_path}: {e}")
                return jsonify({'error': f'Не удалось загрузить файл: {str(e)}'}), 507  # Insufficient Storage
            except Exception as e:
                current_app.logger.exception(f"Ошибка загрузки {user_path}: {e}")
                return jsonify({'error': f'Ошибка загрузки файла: {str(e)}'}), 500
    
    current_app.logger.info(f"Загружено файлов: {len(uploaded_files)}")
    return jsonify({
        'success': True,
        'uploaded_files': uploaded_files,
        'count': len(uploaded_files)
    })


@files_bp.route('/delete/<path:filepath>', methods=['DELETE'])
def delete_file(filepath):
    """Мягкое удаление файла (user_documents.is_soft_deleted=TRUE). ИНКРЕМЕНТ 020 - Блок 9."""
    try:
        from webapp.db.models import UserDocument
        from sqlalchemy import and_
        
        decoded_filepath = unquote(filepath)
        user_id = required_user_id()
        current_app.logger.info(f"Попытка удалить файл: {decoded_filepath} для user_id={user_id}")
        
        db = _get_db()
        
        # Ищем user_document по user_path
        user_doc = db.query(UserDocument).filter(
            and_(
                UserDocument.user_id == user_id,
                UserDocument.user_path == decoded_filepath,
                UserDocument.is_soft_deleted == False
            )
        ).first()
        
        if not user_doc:
            current_app.logger.warning(f"Файл не найден: {decoded_filepath}")
            return jsonify({'error': 'Файл не найден'}), 404
        
        # Мягкое удаление
        user_doc.is_soft_deleted = True
        user_doc.updated_at = datetime.utcnow()
        db.commit()
        
        current_app.logger.info(f"Файл {decoded_filepath} помечен удалённым для user_id={user_id}")
        return jsonify({'success': True})
            
    except Exception as e:
        db.rollback()
        current_app.logger.exception(f"Ошибка при удалении файла: {str(e)}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/delete_folder/<path:folder_path>', methods=['DELETE'])
def delete_folder(folder_path):
    """Мягкое удаление папки (всех файлов в папке). ИНКРЕМЕНТ 020 - Блок 9."""
    try:
        from webapp.db.models import UserDocument
        from sqlalchemy import and_, or_
        
        decoded_folder_path = unquote(folder_path)
        user_id = required_user_id()
        current_app.logger.info(f"Попытка удалить папку: {decoded_folder_path} для user_id={user_id}")
        
        db = _get_db()
        
        if decoded_folder_path == 'root':
            # Удаление всех файлов пользователя
            user_docs = db.query(UserDocument).filter(
                and_(
                    UserDocument.user_id == user_id,
                    UserDocument.is_soft_deleted == False
                )
            ).all()
            
            message = f'Помечено удалёнными {len(user_docs)} файлов'
        else:
            # Удаление файлов в конкретной папке
            # user_path начинается с decoded_folder_path или равен ему
            pattern = f"{decoded_folder_path}/%"
            user_docs = db.query(UserDocument).filter(
                and_(
                    UserDocument.user_id == user_id,
                    UserDocument.is_soft_deleted == False,
                    or_(
                        UserDocument.user_path == decoded_folder_path,
                        UserDocument.user_path.like(pattern)
                    )
                )
            ).all()
            
            message = f'Папка "{decoded_folder_path}" помечена удалённой ({len(user_docs)} файлов)'
        
        # Мягкое удаление всех найденных документов
        for user_doc in user_docs:
            user_doc.is_soft_deleted = True
            user_doc.updated_at = datetime.utcnow()
        
        db.commit()
        
        current_app.logger.info(message)
        
        return jsonify({
            'success': True,
            'message': message,
            'deleted_count': len(user_docs)
        })
        
    except Exception as e:
        db.rollback()
        current_app.logger.exception(f"Ошибка при удалении папки: {str(e)}")
        return jsonify({'error': f'Ошибка удаления папки: {str(e)}'}), 500


@files_bp.get('/download/<path:filepath>')
def download_file(filepath: str):
    """Выдача файла из БД (documents.blob). ИНКРЕМЕНТ 020 - Блок 9."""
    try:
        from io import BytesIO
        from webapp.db.models import Document, UserDocument
        from sqlalchemy import and_
        
        decoded_filepath = unquote(filepath)
        user_id = required_user_id()
        
        db = _get_db()
        
        # Ищем документ по user_path через JOIN
        result = db.query(Document, UserDocument).join(
            UserDocument, UserDocument.document_id == Document.id
        ).filter(
            and_(
                UserDocument.user_id == user_id,
                UserDocument.user_path == decoded_filepath,
                UserDocument.is_soft_deleted == False
            )
        ).first()
        
        if not result:
            return jsonify({'error': 'Файл не найден'}), 404
        
        document, user_doc = result
        
        if not document.blob:
            return jsonify({'error': 'Файл не найден в БД'}), 404
        
        # Извлекаем имя файла и расширение
        fname = os.path.basename(decoded_filepath)
        ext = os.path.splitext(fname)[1].lower().lstrip('.')
        
        # Блокируем скачивание неподдерживаемых форматов (кроме PREVIEW_INLINE_EXTENSIONS)
        if not allowed_file(decoded_filepath, current_app.config['ALLOWED_EXTENSIONS']) and ext not in current_app.config.get('PREVIEW_INLINE_EXTENSIONS', set()):
            return jsonify({'error': 'Неподдерживаемый тип файла'}), 403
        
        # Определяем, можно ли отображать inline
        inline = ext in current_app.config.get('PREVIEW_INLINE_EXTENSIONS', set())
        
        # Преобразуем memoryview в bytes
        blob_bytes = bytes(document.blob) if not isinstance(document.blob, bytes) else document.blob
        file_size = len(blob_bytes)
        
        # Range support для больших файлов
        range_header = request.headers.get('Range')
        if range_header:
            import re
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                
                data = blob_bytes[start:end+1]
                
                resp = Response(data, 206, mimetype=document.mime or 'application/octet-stream')
                resp.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                resp.headers['Accept-Ranges'] = 'bytes'
                resp.headers['Content-Length'] = str(length)
                return resp
        
        # Обычная отдача файла из blob
        blob_io = BytesIO(blob_bytes)
        resp = send_file(
            blob_io,
            mimetype=document.mime or 'application/octet-stream',
            as_attachment=not inline,
            download_name=fname
        )
        
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
    """Мягкое удаление всех документов пользователя. ИНКРЕМЕНТ 020 - Блок 9."""
    try:
        from webapp.db.models import UserDocument
        from sqlalchemy import and_
        
        user_id = required_user_id()
        db = _get_db()
        
        # Помечаем все документы пользователя удалёнными
        user_docs = db.query(UserDocument).filter(
            and_(
                UserDocument.user_id == user_id,
                UserDocument.is_soft_deleted == False
            )
        ).all()
        
        deleted_count = len(user_docs)
        
        for user_doc in user_docs:
            user_doc.is_soft_deleted = True
            user_doc.updated_at = datetime.utcnow()
        
        db.commit()
        
        current_app.logger.info(f"Очистка завершена: помечено удалёнными {deleted_count} документов для user_id={user_id}")
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'index_deleted': False,  # Legacy compatibility
            'errors': []
        })
        
    except Exception as e:
        db.rollback()
        current_app.logger.exception('Ошибка при полной очистке')
        return jsonify({'success': False, 'error': str(e)}), 500


@files_bp.get('/files_json')
def files_json():
    """JSON-дерево файлов из БД (user_documents). ИНКРЕМЕНТ 020 - Блок 9."""
    try:
        from webapp.db.models import Document, UserDocument
        from sqlalchemy import and_
        
        user_id = required_user_id()
        db = _get_db()
        
        # Получаем все не удалённые документы пользователя
        results = db.query(UserDocument, Document).join(
            Document, Document.id == UserDocument.document_id
        ).filter(
            and_(
                UserDocument.user_id == user_id,
                UserDocument.is_soft_deleted == False
            )
        ).all()
        
        # Строим дерево из user_path
        tree = {'folders': {}, 'files': []}
        total_files = 0
        allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
        
        for user_doc, document in results:
            user_path = user_doc.user_path or user_doc.original_filename
            
            # Разбиваем путь на части
            parts = user_path.split('/')
            filename = parts[-1]
            folder_parts = parts[:-1]
            
            # Навигируем к нужной папке в дереве
            current_level = tree
            for folder_name in folder_parts:
                if folder_name not in current_level['folders']:
                    current_level['folders'][folder_name] = {'folders': {}, 'files': []}
                current_level = current_level['folders'][folder_name]
            
            # Добавляем файл
            file_info = {
                'name': filename,
                'path': user_path,
                'size': document.size_bytes,
                'document_id': document.id
            }
            
            # Проверяем поддержку формата
            if not allowed_file(filename, allowed_extensions):
                file_info['unsupported'] = True
            
            current_level['files'].append(file_info)
            total_files += 1
        
        return jsonify({
            'tree': tree,
            'total_files': total_files,
            'file_statuses': {}  # Legacy compatibility
        })
    
    except Exception as e:
        current_app.logger.exception('files_json error')
        return jsonify({'error': str(e)}), 500

