"""
Сервис индексации в БД с инкрементальной обработкой и дедупликацией.

Реализует спецификацию 015:
- Расчёт root_hash для папок (инкрементальная индексация)
- Измерение indexing_cost_seconds
- Поддержка дедупликации по sha256
- Работа с таблицами documents, chunks, folder_index_status
"""
import os
import hashlib
import time
from typing import List, Dict, Any, Optional, Tuple
from flask import current_app
from webapp.models.rag_models import RAGDatabase
from webapp.services.chunking import chunk_document
from document_processor.extractors.text_extractor import extract_text


def calculate_file_hash(file_path: str) -> str:
    """
    Вычисляет SHA256 хеш файла.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Строка с SHA256 хешем (64 символа)
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
    except Exception as e:
        current_app.logger.warning(f'Ошибка хеширования {file_path}: {e}')
        return ""
    return sha256.hexdigest()


def calculate_root_hash(folder_path: str) -> str:
    """
    Вычисляет root_hash для папки.
    
    Root hash = SHA256 от конкатенации (filename + mtime + size) всех файлов.
    Используется для определения изменений в папке.
    
    Args:
        folder_path: Путь к папке
        
    Returns:
        Строка с SHA256 хешем папки
    """
    if not os.path.exists(folder_path):
        return ""
    
    file_infos = []
    try:
        for root, _, files in os.walk(folder_path):
            for filename in sorted(files):  # сортировка для детерминизма
                file_path = os.path.join(root, filename)
                try:
                    stat = os.stat(file_path)
                    # Относительный путь для стабильности
                    rel_path = os.path.relpath(file_path, folder_path)
                    info_str = f"{rel_path}|{stat.st_mtime}|{stat.st_size}"
                    file_infos.append(info_str)
                except Exception as e:
                    current_app.logger.debug(f'Пропуск файла {file_path}: {e}')
                    continue
    except Exception as e:
        current_app.logger.warning(f'Ошибка обхода папки {folder_path}: {e}')
        return ""
    
    # Конкатенация и хеширование
    combined = "\n".join(file_infos)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def get_folder_index_status(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str
) -> Optional[Dict[str, Any]]:
    """
    Получает статус индексации папки из БД.
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        folder_path: Путь к папке
        
    Returns:
        Словарь со статусом или None если не найдено
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, root_hash, last_indexed_at
                    FROM folder_index_status
                    WHERE owner_id = %s AND folder_path = %s;
                """, (owner_id, folder_path))
                
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'root_hash': row[1],
                        'last_indexed_at': row[2]
                    }
    except Exception as e:
        current_app.logger.error(f'Ошибка получения статуса индексации: {e}')
    return None


def update_folder_index_status(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str,
    root_hash: str
) -> None:
    """
    Обновляет статус индексации папки в БД.
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        folder_path: Путь к папке
        root_hash: Новый root_hash папки
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO folder_index_status (owner_id, folder_path, root_hash, last_indexed_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (owner_id, folder_path)
                    DO UPDATE SET
                        root_hash = EXCLUDED.root_hash,
                        last_indexed_at = CURRENT_TIMESTAMP;
                """, (owner_id, folder_path, root_hash))
            conn.commit()
    except Exception as e:
        current_app.logger.error(f'Ошибка обновления статуса индексации: {e}')
        raise


def find_changed_files(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str,
    current_files: Dict[str, Dict[str, Any]]
) -> List[str]:
    """
    Определяет список изменённых файлов (новые или изменённые по sha256).
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        folder_path: Путь к папке
        current_files: Словарь {file_path: {'sha256': ..., 'size': ..., 'mtime': ...}}
        
    Returns:
        Список путей к изменённым файлам
    """
    changed_files = []
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Получаем sha256 всех видимых документов владельца.
                # Используем storage_url, так как он хранит относительный путь в uploads.
                cur.execute("""
                    SELECT storage_url, sha256
                    FROM documents
                    WHERE owner_id = %s AND is_visible = TRUE;
                """, (owner_id,))
                rows = cur.fetchall()
                existing_hashes = {row[0]: row[1] for row in rows if row[0]}
                current_app.logger.info(f'[CHANGED] В БД найдено {len(existing_hashes)} документов: {list(existing_hashes.keys())[:3]}...')
        
        # Сравниваем хеши
        for file_path, file_info in current_files.items():
            # Преобразуем абсолютный путь файла к относительному пути внутри папки индексации
            try:
                rel_path = os.path.relpath(file_path, folder_path)
            except Exception:
                rel_path = os.path.basename(file_path)
            existing_hash = existing_hashes.get(rel_path)
            current_hash = file_info.get('sha256')
            
            if existing_hash != current_hash:
                changed_files.append(file_path)
                
    except Exception as e:
        current_app.logger.error(f'Ошибка определения изменённых файлов: {e}')
        # В случае ошибки индексируем все файлы
        changed_files = list(current_files.keys())
    
    return changed_files


def index_document_to_db(
    db: RAGDatabase,
    owner_id: int,
    file_path: str,
    file_info: Dict[str, Any],
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50
) -> Tuple[int, float]:
    """
    Индексирует один документ в БД с измерением времени.
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        file_path: Путь к файлу
        file_info: Метаданные файла {'sha256': ..., 'size': ..., 'content_type': ...}
        chunk_size_tokens: Размер чанка в токенах
        chunk_overlap_tokens: Перекрытие чанков
        
    Returns:
        Tuple[document_id, indexing_cost_seconds]
    """
    start_time = time.time()
    
    try:
        # 1. Проверка существования документа по sha256 (дедупликация на уровне файла)
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM documents
                    WHERE owner_id = %s AND sha256 = %s AND is_visible = TRUE;
                """, (owner_id, file_info['sha256']))
                
                existing_doc = cur.fetchone()
                if existing_doc:
                    # Документ уже проиндексирован, возвращаем существующий ID
                    indexing_cost = time.time() - start_time
                    current_app.logger.info(f'Документ {file_path} уже проиндексирован (дедупликация)')
                    return existing_doc[0], indexing_cost
        
        # 2. Извлекаем текст через общий экстрактор и чанкуем
        content = ""
        try:
            current_app.logger.info(f'[EXTRACT] Вызов extract_text для: {file_path}, exists={os.path.exists(file_path)}')
            content = extract_text(file_path) or ""
            current_app.logger.info(f'[EXTRACT] extract_text вернул {len(content)} символов')
        except Exception as e:
            current_app.logger.warning(f'Ошибка извлечения текста {file_path}: {e}')
        
        if not content:
            try:
                ext = os.path.splitext(file_path)[1].lower()
            except Exception:
                ext = ''
            current_app.logger.info(f'Пропуск индексации: пустой контент после чтения (возможно, неподдерживаемый формат) file={file_path}, ext={ext}')
            indexing_cost = time.time() - start_time
            return 0, indexing_cost
        
    # 3. Чанкуем текст
        current_app.logger.info(f'[CHUNK] Начинаем чанкование для {file_path}, size_tokens={chunk_size_tokens}')
        chunks = chunk_document(
            content,
            file_path=file_path,
            chunk_size_tokens=chunk_size_tokens,
            overlap_sentences=2  # TODO: использовать chunk_overlap_tokens
        )
        current_app.logger.info(f'[CHUNK] Получено {len(chunks)} чанков')
        
        if not chunks:
            current_app.logger.info(f'Чанкование вернуло 0 чанков: {file_path}')
            indexing_cost = time.time() - start_time
            return 0, indexing_cost
        
        # 4. Добавляем документ в БД
        # Сохраняем относительный путь (storage_url) для последующего отображения через /view
        uploads_root = current_app.config.get('UPLOAD_FOLDER')
        try:
            if uploads_root:
                # Если файл лежит в пределах uploads, сохраняем относительный путь
                abs_file = os.path.abspath(file_path)
                abs_root = os.path.abspath(uploads_root)
                if os.path.commonpath([abs_file, abs_root]) == abs_root:
                    storage_url = os.path.relpath(abs_file, abs_root)
                else:
                    storage_url = os.path.basename(file_path)
            else:
                storage_url = os.path.basename(file_path)
        except Exception:
            storage_url = os.path.basename(file_path)
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO documents (
                        owner_id, original_filename, storage_url, content_type, size_bytes, sha256,
                        status, uploaded_at, indexed_at, is_visible, access_count, indexing_cost_seconds
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, 'indexed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE, 0, %s
                    )
                    RETURNING id;
                """, (
                    owner_id,
                    os.path.basename(file_path),
                    storage_url,
                    file_info.get('content_type', 'text/plain'),
                    file_info.get('size', 0),
                    file_info['sha256'],
                    time.time() - start_time  # предварительная оценка
                ))
                
                doc_id = cur.fetchone()[0]
            conn.commit()
        
        # 5. Добавляем чанки в БД
        chunk_data = []
        for idx, chunk in enumerate(chunks):
            # chunk_document возвращает 'content', а не 'text'
            text = chunk.get('content', chunk.get('text', ''))
            chunk_sha256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
            chunk_data.append({
                'document_id': doc_id,
                'owner_id': owner_id,
                'chunk_idx': idx,
                'text': text,
                'text_sha256': chunk_sha256,
                'tokens': chunk.get('token_count', chunk.get('tokens', 0)),
                'embedding': None  # TODO: генерация эмбеддингов
            })
        
        if chunk_data:
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    # Удаляем старые чанки документа
                    cur.execute("DELETE FROM chunks WHERE document_id = %s;", (doc_id,))
                    
                    # Вставляем новые чанки
                    from psycopg2.extras import execute_values
                    execute_values(
                        cur,
                        """
                        INSERT INTO chunks (document_id, owner_id, chunk_idx, text, text_sha256, tokens, created_at)
                        VALUES %s;
                        """,
                        [(c['document_id'], c['owner_id'], c['chunk_idx'], c['text'], c['text_sha256'], c['tokens'], 'now()') 
                         for c in chunk_data]
                    )
                conn.commit()
        
        # 6. Финальное обновление indexing_cost_seconds
        indexing_cost = time.time() - start_time
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE documents
                    SET indexing_cost_seconds = %s
                    WHERE id = %s;
                    """,
                    (indexing_cost, doc_id)
                )
            conn.commit()
        
        current_app.logger.info(
            f'Документ {file_path} проиндексирован: ID={doc_id}, {len(chunks)} чанков, {indexing_cost:.2f}с'
        )
        return doc_id, indexing_cost
        
    except Exception:
        indexing_cost = time.time() - start_time
        current_app.logger.exception(f'Ошибка индексации {file_path}')
        return 0, indexing_cost


def build_db_index(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50,
    force_rebuild: bool = False
) -> Tuple[bool, str, Dict[str, int]]:
    """
    Инкрементальная индексация папки в БД.
    
    Алгоритм:
    1. Вычисляем root_hash текущей папки
    2. Сравниваем с сохранённым в folder_index_status
    3. Если совпадает И force_rebuild=False — пропускаем индексацию
    4. Иначе определяем изменённые файлы и индексируем только их
    5. Обновляем folder_index_status
    
    Args:
        force_rebuild: Если True, игнорирует root_hash и пересобирает индекс
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        folder_path: Путь к папке для индексации
        chunk_size_tokens: Размер чанка
        chunk_overlap_tokens: Перекрытие чанков
        
    Returns:
        Tuple[success, message, stats]
    """
    try:
        # 1. Вычисляем текущий root_hash
        current_root_hash = calculate_root_hash(folder_path)
        if not current_root_hash:
            return False, f'Не удалось вычислить root_hash для {folder_path}', {}
        
        # 2. Проверяем статус индексации и количество документов
        status = get_folder_index_status(db, owner_id, folder_path)
        
        # Проверяем наличие документов в БД для этого владельца
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM documents
                    WHERE owner_id = %s AND is_visible = TRUE;
                """, (owner_id,))
                docs_count = cur.fetchone()[0]
        
        # Если есть статус, root_hash совпадает, НЕ force_rebuild И есть документы — пропускаем
        if not force_rebuild and status and status['root_hash'] == current_root_hash and docs_count > 0:
            current_app.logger.info(f'Папка {folder_path} не изменилась (root_hash совпадает, документов: {docs_count}), пропускаем индексацию')
            return True, 'Индексация не требуется (папка не изменилась)', {}
        
        if force_rebuild:
            current_app.logger.info(f'Принудительная пересборка индекса для {folder_path}')
        if docs_count == 0:
            current_app.logger.info(f'Документов нет в БД, принудительная индексация папки {folder_path}')
        
        # 3. Собираем информацию о всех файлах в папке
        current_files = {}
        for root, _, files in os.walk(folder_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                try:
                    file_hash = calculate_file_hash(file_path)
                    file_stat = os.stat(file_path)
                    current_files[file_path] = {
                        'sha256': file_hash,
                        'size': file_stat.st_size,
                        'mtime': file_stat.st_mtime,
                        'content_type': 'text/plain'  # TODO: определение типа
                    }
                except Exception as e:
                    current_app.logger.warning(f'Пропуск файла {file_path}: {e}')
                    continue
        
        if not current_files:
            return False, 'Нет файлов для индексации', {}
        
        # 4. Определяем изменённые файлы
        changed_files = find_changed_files(db, owner_id, folder_path, current_files)
        current_app.logger.info(f'[CHANGED] Обнаружено {len(changed_files)} изменённых файлов из {len(current_files)}')
        
        if not changed_files:
            # Файлы не изменились, но root_hash изменился (возможно, переименование/перемещение)
            update_folder_index_status(db, owner_id, folder_path, current_root_hash)
            return True, 'Изменений в файлах не обнаружено', {}
        
        # 5. Индексируем изменённые файлы
        stats = {
            'total_files': len(current_files),
            'changed_files': len(changed_files),
            'indexed_documents': 0,
            'total_cost_seconds': 0.0
        }
        
        for file_path in changed_files:
            file_info = current_files[file_path]
            doc_id, cost = index_document_to_db(
                db, owner_id, file_path, file_info,
                chunk_size_tokens, chunk_overlap_tokens
            )
            if doc_id > 0:
                stats['indexed_documents'] += 1
            stats['total_cost_seconds'] += cost
        
        # 6. Обновляем статус индексации папки
        update_folder_index_status(db, owner_id, folder_path, current_root_hash)
        
        message = f"Проиндексировано {stats['indexed_documents']} из {stats['changed_files']} изменённых файлов"
        current_app.logger.info(f'{message}, время: {stats["total_cost_seconds"]:.2f}с')
        
        return True, message, stats
        
    except Exception as e:
        current_app.logger.exception('Ошибка индексации в БД')
        return False, str(e), {}


def check_document_exists_by_hash(db: RAGDatabase, sha256_hash: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет, существует ли документ с таким SHA256 в БД.
    
    Args:
        db: Подключение к БД
        sha256_hash: SHA256 хеш файла
        
    Returns:
        Dict с полями документа если найден, None если нет
        Поля: id, owner_id, original_filename, is_visible, deleted_at, sha256
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, owner_id, original_filename, is_visible, deleted_at, sha256
                    FROM documents
                    WHERE sha256 = %s
                    LIMIT 1;
                """, (sha256_hash,))
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'owner_id': row[1],
                        'original_filename': row[2],
                        'is_visible': row[3],
                        'deleted_at': row[4],
                        'sha256': row[5]
                    }
                return None
    except Exception as e:
        current_app.logger.warning(f'Ошибка проверки дубликата по sha256: {e}')
        return None


def restore_soft_deleted_document(db: RAGDatabase, document_id: int, new_owner_id: int, new_filename: str) -> bool:
    """
    Восстанавливает мягко удалённый документ (is_visible=FALSE → TRUE).
    
    Args:
        db: Подключение к БД
        document_id: ID документа для восстановления
        new_owner_id: ID нового владельца (может совпадать со старым)
        new_filename: Новое имя файла
        
    Returns:
        True если восстановлено, False если ошибка
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documents
                    SET is_visible = TRUE,
                        deleted_at = NULL,
                        owner_id = %s,
                        original_filename = %s,
                        last_accessed_at = NOW()
                    WHERE id = %s;
                """, (new_owner_id, new_filename, document_id))
            conn.commit()
        current_app.logger.info(f'Восстановлен документ #{document_id} для owner_id={new_owner_id}')
        return True
    except Exception:
        current_app.logger.exception(f'Ошибка восстановления документа #{document_id}')
        return False


def copy_chunks_between_users(db: RAGDatabase, source_doc_id: int, target_doc_id: int) -> int:
    """
    Копирует чанки от одного документа к другому (для дедупликации между пользователями).
    
    Args:
        db: Подключение к БД
        source_doc_id: ID документа-источника
        target_doc_id: ID документа-назначения
        
    Returns:
        Количество скопированных чанков
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Копируем чанки, заполняя owner_id целевого документа и сохраняя text_sha256/tokens, если они есть
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, owner_id, chunk_idx, text, text_sha256, tokens)
                    SELECT %s AS document_id,
                           d.owner_id AS owner_id,
                           c.chunk_idx,
                           c.text,
                           c.text_sha256,
                           c.tokens
                    FROM chunks c
                    JOIN documents d ON d.id = %s
                    WHERE c.document_id = %s;
                    """,
                    (target_doc_id, target_doc_id, source_doc_id)
                )
                count = cur.rowcount
            conn.commit()
        current_app.logger.info(f'Скопировано {count} чанков: doc#{source_doc_id} → doc#{target_doc_id}')
        return count
    except Exception:
        current_app.logger.exception(f'Ошибка копирования чанков: doc#{source_doc_id} → doc#{target_doc_id}')
        return 0


def handle_duplicate_upload(
    db: RAGDatabase,
    owner_id: int,
    file_path: str,
    sha256_hash: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50
) -> Tuple[int, str, bool]:
    """
    Обрабатывает загрузку дубликата файла (дедупликация).
    
    Сценарии:
    1. Документ с таким sha256 уже существует у того же пользователя и видим → пропускаем
    2. Документ мягко удалён у того же пользователя → восстанавливаем
    3. Документ существует у другого пользователя → создаём новую запись, копируем чанки
    4. Документа нет → индексируем как обычно
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        file_path: Путь к файлу
        sha256_hash: SHA256 хеш файла
        chunk_size_tokens: Размер чанка в токенах
        chunk_overlap_tokens: Перекрытие чанков в токенах
        
    Returns:
        Tuple (document_id, message, is_duplicate)
    """
    filename = os.path.basename(file_path)
    
    # Проверяем существование документа
    existing_doc = check_document_exists_by_hash(db, sha256_hash)
    
    if not existing_doc:
        # Сценарий 4: документа нет → индексируем обычным образом
        file_info = {
            'sha256': sha256_hash,
            'mtime': os.path.getmtime(file_path),
            'size': os.path.getsize(file_path),
            'content_type': 'text/plain'  # TODO: определение MIME
        }
        doc_id, _ = index_document_to_db(
            db, owner_id, file_path, file_info,
            chunk_size_tokens, chunk_overlap_tokens
        )
        return doc_id, 'Новый документ проиндексирован', False
    
    # Документ существует
    if existing_doc['owner_id'] == owner_id:
        if existing_doc['is_visible']:
            # Сценарий 1: уже существует у пользователя и видим
            current_app.logger.info(f'Дубликат пропущен: {filename} (doc#{existing_doc["id"]})')
            return existing_doc['id'], 'Документ уже существует (пропущен)', True
        else:
            # Сценарий 2: мягко удалён у того же пользователя → восстанавливаем
            if restore_soft_deleted_document(db, existing_doc['id'], owner_id, filename):
                return existing_doc['id'], 'Документ восстановлен из архива', True
            else:
                return -1, 'Ошибка восстановления документа', False
    else:
        # Сценарий 3: существует у другого пользователя → создаём новую запись, копируем чанки
        try:
            # Рассчитываем storage_url (относительный путь в пределах uploads)
            uploads_root = current_app.config.get('UPLOAD_FOLDER')
            try:
                if uploads_root:
                    abs_file = os.path.abspath(file_path)
                    abs_root = os.path.abspath(uploads_root)
                    if os.path.commonpath([abs_file, abs_root]) == abs_root:
                        storage_url = os.path.relpath(abs_file, abs_root)
                    else:
                        storage_url = os.path.basename(file_path)
                else:
                    storage_url = os.path.basename(file_path)
            except Exception:
                storage_url = os.path.basename(file_path)
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO documents (owner_id, original_filename, storage_url, sha256, is_visible, indexing_cost_seconds)
                        VALUES (%s, %s, %s, %s, TRUE, 0.0)
                        RETURNING id;
                    """, (owner_id, filename, storage_url, sha256_hash))
                    new_doc_id = cur.fetchone()[0]
                conn.commit()
            
            # Копируем чанки от существующего документа
            count = copy_chunks_between_users(db, existing_doc['id'], new_doc_id)
            msg = f'Дубликат добавлен для нового пользователя ({count} чанков скопировано)'
            current_app.logger.info(f'{msg}: doc#{existing_doc["id"]} → doc#{new_doc_id}')
            return new_doc_id, msg, True
            
        except Exception as e:
            current_app.logger.exception(f'Ошибка создания дубликата для owner_id={owner_id}')
            return -1, f'Ошибка дедупликации: {e}', False
