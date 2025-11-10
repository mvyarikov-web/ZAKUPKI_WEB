"""
Сервис индексации в БД с инкрементальной обработкой и дедупликацией.

Реализует спецификацию 015:
- Расчёт root_hash для папок (инкрементальная индексация)
- Измерение indexing_cost_seconds
- Поддержка дедупликации по sha256
- Работа с таблицами documents, chunks, folder_index_status
- Извлечение текста из documents.blob (режим pure DB)
"""
import os
import hashlib
import time
from typing import List, Dict, Any, Optional, Tuple
from flask import current_app
from webapp.models.rag_models import RAGDatabase
from webapp.services.chunking import chunk_document
from document_processor.extractors.text_extractor import extract_text_from_bytes
from webapp.utils.path_utils import normalize_path, get_relative_path


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
    """Статус индексации папки (перенесено на новую схему: folder_index_status остаётся привязанной к пользователю).

    user_documents влияет только на видимость документов, но root_hash и время индексации считаем на пользователя.
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
    """Определяет список изменённых файлов для пользователя.

    Новая модель: documents глобальные, видимость через user_documents.
    Сравниваем sha256 текущих файлов с sha256 связанных документов пользователя.
    """
    changed_files = []
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Получаем связи пользователя -> документ + относительный путь
                cur.execute("""
                    SELECT ud.user_path, d.sha256
                    FROM user_documents ud
                    JOIN documents d ON d.id = ud.document_id
                    WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE;
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
    file_path: str,
    file_info: dict,
    user_id: int,
    original_filename: str,
    user_path: str,
    chunk_size_tokens: int = 800,
    chunk_overlap_tokens: int = 50
) -> Tuple[int, float]:
    """Индексирует документ в БД: создаёт documents, user_documents и chunks.
    
    Args:
        db: экземпляр RAGDatabase
        file_path: путь к файлу
        file_info: метаданные файла (sha256, size, content_type...)
        user_id: ID пользователя
        original_filename: исходное имя файла
        user_path: путь пользователя (относительно uploads)
        chunk_size_tokens: размер чанка в токенах
        chunk_overlap_tokens: перекрытие между чанками (TODO)
    
    Returns:
        (document_id, indexing_cost_seconds)
    """
    start_time = time.time()
    
    try:
        # 1. Проверка существования документа по sha256 и получение blob
        document_blob = None
        document_id = None
        has_chunks = False
        
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, blob FROM documents WHERE sha256 = %s;
                """, (file_info['sha256'],))
                row = cur.fetchone()
                if row:
                    document_id = row[0]
                    document_blob = row[1]
                    
                    # Проверяем есть ли chunks у этого документа
                    cur.execute("""
                        SELECT COUNT(*) FROM chunks WHERE document_id = %s;
                    """, (document_id,))
                    chunks_count = cur.fetchone()[0]
                    has_chunks = chunks_count > 0
                    
                    if has_chunks:
                        # Документ уже проиндексирован, возвращаем его ID
                        indexing_cost = time.time() - start_time
                        current_app.logger.info(f'[INDEX] Документ {document_id} уже проиндексирован ({chunks_count} chunks), пропускаем')
                        return document_id, indexing_cost
                    else:
                        current_app.logger.info(f'[INDEX] Документ {document_id} найден, но chunks отсутствуют - выполняем индексацию')
        
        # 2. Извлекаем текст из blob (если есть) или из файла (fallback)
        content = ""
        try:
            if document_blob:
                # Читаем из blob (преобразуем memoryview в bytes)
                blob_bytes = bytes(document_blob) if not isinstance(document_blob, bytes) else document_blob
                current_app.logger.info(f'[EXTRACT] Извлечение текста из blob, размер: {len(blob_bytes)} байт')
                ext = os.path.splitext(original_filename)[1].lower().lstrip('.')
                content = extract_text_from_bytes(blob_bytes, ext) or ""
                current_app.logger.info(f'[EXTRACT] extract_text_from_bytes вернул {len(content)} символов')
            else:
                # Fallback: читаем из файловой системы (временная совместимость)
                current_app.logger.warning(f'[EXTRACT] Blob отсутствует, fallback на чтение из файла: {file_path}')
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                    content = extract_text_from_bytes(file_bytes, ext) or ""
                    current_app.logger.info(f'[EXTRACT] Извлечено {len(content)} символов из файла')
                else:
                    current_app.logger.error(f'[EXTRACT] Файл не найден и blob отсутствует: {file_path}')
        except Exception as e:
            current_app.logger.warning(f'Ошибка извлечения текста {original_filename}: {e}')
        
        if not content:
            # Graceful degrade: создаём осмысленный placeholder, чтобы PDF не выглядел "пустым"
            ext = os.path.splitext(original_filename)[1].lower()
            if ext == '.pdf':
                content = f'[ПУСТОЙ PDF ИЛИ ОШИБКА ИЗВЛЕЧЕНИЯ] {original_filename}'
            else:
                content = original_filename
        
    # 3. Чанкуем текст
        current_app.logger.info(f'[CHUNK] Начинаем чанкование для {file_path}, size_tokens={chunk_size_tokens}')
        chunks = chunk_document(
            content,
            file_path=file_path,
            chunk_size_tokens=chunk_size_tokens,
            overlap_sentences=2  # TODO: использовать chunk_overlap_tokens
        )
        current_app.logger.info(f'[CHUNK] Получено {len(chunks)} чанков')
        
        if not chunks or all(not (c.get('content') or c.get('text')) for c in chunks):
            # Создаём один fallback чанк
            chunks = [{'content': content, 'token_count': len(content.split())}]
        
    # 4. Добавляем документ (глобально) и user_documents связь в ОДНОЙ транзакции
        # Если документ уже существует (но без chunks), используем существующий ID
        if document_id is None:
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    # Создаём глобальный документ
                    cur.execute(
                        """
                        INSERT INTO documents (sha256, size_bytes, mime, parse_status, indexing_cost_seconds)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id;
                        """,
                        (
                            file_info['sha256'],
                            file_info.get('size', 0),
                            file_info.get('content_type', 'text/plain'),
                            'indexed',
                            0.0
                        )
                    )
                    doc_id = cur.fetchone()[0]
                    
                    # Сразу создаём user_documents связь (в той же транзакции!)
                    cur.execute(
                        """
                        INSERT INTO user_documents (user_id, document_id, original_filename, user_path)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, document_id) DO UPDATE
                        SET is_soft_deleted = FALSE, original_filename = EXCLUDED.original_filename, user_path = EXCLUDED.user_path;
                        """,
                        (user_id, doc_id, original_filename, user_path)
                    )
                conn.commit()
        else:
            # Документ уже существует, используем его ID и обновляем связь
            doc_id = document_id
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_documents (user_id, document_id, original_filename, user_path)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, document_id) DO UPDATE
                        SET is_soft_deleted = FALSE, original_filename = EXCLUDED.original_filename, user_path = EXCLUDED.user_path;
                        """,
                        (user_id, doc_id, original_filename, user_path)
                    )
                conn.commit()
        
        # 5. Добавляем чанки в БД
        chunk_data = []
        for idx, chunk in enumerate(chunks):
            text = chunk.get('content', chunk.get('text', ''))
            chunk_sha256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
            chunk_data.append({
                'document_id': doc_id,
                'chunk_index': idx,
                'text': text,
                'text_sha256': chunk_sha256,
                'tokens': chunk.get('token_count', chunk.get('tokens', 0))
            })
        
        current_app.logger.info(f'[CHUNKS] Подготовлено {len(chunk_data)} чанков для записи в БД (doc_id={doc_id})')
        
        if chunk_data:
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    # Удаляем старые чанки документа
                    cur.execute("DELETE FROM chunks WHERE document_id = %s;", (doc_id,))
                    from psycopg2.extras import execute_values
                    execute_values(
                        cur,
                        """
                        INSERT INTO chunks (document_id, chunk_idx, text, tokens, created_at)
                        VALUES %s;
                        """,
                        [
                            (
                                c['document_id'],
                                c['chunk_index'],
                                c['text'],
                                c['tokens']
                            ) for c in chunk_data
                        ],
                        template="(%s, %s, %s, %s, NOW())"
                    )
                conn.commit()
                current_app.logger.info(f'[CHUNKS] Записано {len(chunk_data)} чанков в БД для doc_id={doc_id}')
        
        # 6. Финальное обновление indexing_cost_seconds
        indexing_cost = time.time() - start_time
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE documents SET indexing_cost_seconds = %s WHERE id = %s;", (indexing_cost, doc_id))
            conn.commit()
        
        # 7. Добавляем запись в поисковый индекс search_index
        try:
            from webapp.db.repositories.search_index_repository import SearchIndexRepository
            import json
            
            with db.db.connect() as conn:
                search_repo = SearchIndexRepository(conn)
                metadata = {
                    'original_filename': original_filename,
                    'user_path': user_path,
                    'file_size': file_info.get('size', 0),
                    'content_type': file_info.get('content_type', 'text/plain'),
                    'chunks_count': len(chunks)
                }
                search_repo.create_or_update_index(
                    document_id=doc_id,
                    user_id=user_id,
                    content=content,
                    metadata=metadata
                )
                conn.commit()
            current_app.logger.info(f'[SEARCH_INDEX] Добавлена запись для doc_id={doc_id}, user_id={user_id}')
        except Exception as e:
            current_app.logger.warning(f'Ошибка добавления в search_index: {e}')
            # Не падаем, индексация документа уже прошла успешно
        
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
    """Инкрементальная индексация папки c учётом глобальных документов.

    root_hash остаётся пер-пользовательским (состояние папки пользователя).
    Изменённые файлы определяются сравнением sha256 с теми документами, которые уже привязаны пользователю.
    Новые файлы → индексируем глобально (если отсутствует sha256) + создаём user_documents связь.
    """
    try:
        # 1. Вычисляем текущий root_hash
        current_root_hash = calculate_root_hash(folder_path)
        if not current_root_hash:
            return False, f'Не удалось вычислить root_hash для {folder_path}', {}
        
        # 2. Проверяем статус индексации и количество документов
        status = get_folder_index_status(db, owner_id, folder_path)
        
        # Проверяем наличие видимых документов через связь user_documents
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM user_documents WHERE user_id = %s AND is_soft_deleted = FALSE;
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
        
        from .db_indexing import handle_duplicate_upload  # локальный импорт чтобы избежать циклов
        for file_path in changed_files:
            file_info = current_files[file_path]
            sha256_hash = file_info['sha256']
            doc_id, message, is_dup = handle_duplicate_upload(
                db,
                owner_id,
                file_path,
                sha256_hash,
                chunk_size_tokens,
                chunk_overlap_tokens
            )
            current_app.logger.info(f'[INDEX] {os.path.basename(file_path)}: doc_id={doc_id}, is_dup={is_dup}, msg={message}')
            if doc_id > 0 and not is_dup:
                stats['indexed_documents'] += 1
            stats['total_cost_seconds'] += 0  # стоимость уже учтена внутри index_document_to_db
        
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


def ensure_user_binding(
    db: RAGDatabase,
    user_id: int,
    document_id: int,
    original_filename: str,
    user_path: str
) -> Tuple[bool, str]:
    """Создаёт или обновляет связь пользователя с документом.

    Возвращает (is_new_binding, message).
    Если была soft-deleted запись – восстанавливает.
    """
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT is_soft_deleted FROM user_documents
                    WHERE user_id = %s AND document_id = %s;
                    """,
                    (user_id, document_id)
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        """
                        INSERT INTO user_documents (user_id, document_id, original_filename, user_path)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (user_id, document_id, original_filename, user_path)
                    )
                    conn.commit()
                    return True, 'Связь создана'
                elif row[0]:  # была soft-deleted
                    cur.execute(
                        """
                        UPDATE user_documents
                        SET is_soft_deleted = FALSE, original_filename = %s, user_path = %s
                        WHERE user_id = %s AND document_id = %s;
                        """,
                        (original_filename, user_path, user_id, document_id)
                    )
                    conn.commit()
                    return False, 'Связь восстановлена'
                else:
                    return False, 'Связь уже существует'
    except Exception:
        current_app.logger.exception('Ошибка ensure_user_binding')
        return False, 'Ошибка связывания'


def handle_duplicate_upload(
    db: RAGDatabase,
    user_id: int,
    file_path: str,
    sha256_hash: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50
) -> Tuple[int, str, bool]:
    """Глобальный дедуп: один документ на sha256, видимость через user_documents.

    Возвращает (document_id, message, is_duplicate).
    """
    filename = os.path.basename(file_path)

    # Относительный путь для user_path (в пределах uploads) с нормализацией
    uploads_root = current_app.config.get('UPLOAD_FOLDER')
    if uploads_root:
        user_path = get_relative_path(file_path, uploads_root)
    else:
        user_path = normalize_path(os.path.basename(file_path))

    # Проверяем существование глобального документа
    with db.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE sha256 = %s;", (sha256_hash,))
            row = cur.fetchone()
            doc_id = row[0] if row else None

    if not doc_id:
        # Новый документ: индексируем (создаём документ + чанки)
        file_info = {
            'sha256': sha256_hash,
            'size': os.path.getsize(file_path),
            'content_type': 'text/plain'
        }
        doc_id, _ = index_document_to_db(
            db,
            file_path,
            file_info,
            user_id,
            filename,
            user_path,
            chunk_size_tokens,
            chunk_overlap_tokens
        )
        # user_documents связь уже создана внутри index_document_to_db
        return doc_id, 'Документ создан и привязан к пользователю', False

    # Документ существует глобально → создаём/обновляем связь
    binding_new, bind_msg = ensure_user_binding(db, user_id, doc_id, filename, user_path)
    return doc_id, bind_msg, True


def rebuild_all_documents(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50
) -> Tuple[bool, str, Dict[str, int]]:
    """Полная пересборка индекса всех документов пользователя.
    
    Сканирует папку folder_path, находит документы в БД по SHA256,
    перечитывает текст заново и перезаписывает chunks.
    
    Args:
        db: Подключение к БД
        owner_id: ID пользователя
        folder_path: Корневая папка с файлами (uploads или подпапка)
        chunk_size_tokens: Размер чанка
        chunk_overlap_tokens: Перекрытие чанков
    
    Returns:
        (success, message, stats)
    """
    try:
        stats = {
            'total_docs': 0,
            'reindexed': 0,
            'skipped_empty': 0,
            'errors': 0
        }
        
        # Сканируем папку и находим все файлы
        files_to_process = []
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                # Пропускаем служебные файлы
                if filename.startswith('.') or filename.startswith('~$') or filename == '_search_index.txt':
                    continue
                file_path = os.path.join(root, filename)
                files_to_process.append((file_path, filename))
        
        stats['total_docs'] = len(files_to_process)
        current_app.logger.info(f"Пересборка индекса: найдено {len(files_to_process)} файлов в {folder_path} для user_id={owner_id}")
        
        for file_path, filename in files_to_process:
            try:
                # Вычисляем SHA256 файла
                file_sha256 = calculate_file_hash(file_path)
                if not file_sha256:
                    current_app.logger.warning(f"Не удалось вычислить SHA256 для {filename}, пропускаем")
                    stats['errors'] += 1
                    continue
                
                # Ищем документ в БД по SHA256 и owner_id, получаем blob
                document_blob = None
                with db.db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT ud.document_id, d.sha256, d.blob
                            FROM user_documents ud
                            JOIN documents d ON d.id = ud.document_id
                            WHERE ud.user_id = %s AND d.sha256 = %s AND ud.is_soft_deleted = FALSE
                            LIMIT 1;
                        """, (owner_id, file_sha256))
                        doc_row = cur.fetchone()
                
                if not doc_row:
                    current_app.logger.debug(f"Документ {filename} (SHA256={file_sha256[:8]}...) не найден в БД, пропускаем")
                    stats['errors'] += 1
                    continue
                
                doc_id = doc_row[0]
                document_blob = doc_row[2]
                
                # Извлекаем текст из blob или файла (fallback)
                start = time.time()
                text = ""
                try:
                    if document_blob:
                        # Преобразуем memoryview в bytes
                        blob_bytes = bytes(document_blob) if not isinstance(document_blob, bytes) else document_blob
                        ext = os.path.splitext(filename)[1].lower().lstrip('.')
                        text = extract_text_from_bytes(blob_bytes, ext) or ""
                    else:
                        # Fallback: чтение из файла
                        current_app.logger.warning(f"Blob отсутствует для {filename}, fallback на файл")
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                file_bytes = f.read()
                            ext = os.path.splitext(filename)[1].lower().lstrip('.')
                            text = extract_text_from_bytes(file_bytes, ext) or ""
                except Exception as e:
                    current_app.logger.error(f"Ошибка извлечения текста для {filename}: {e}")
                
                extract_time = time.time() - start
                
                if not text or len(text.strip()) == 0:
                    current_app.logger.warning(f"Пустой текст из {filename}, пропускаем")
                    stats['skipped_empty'] += 1
                    continue
                
                # Создаём чанки
                chunks_data = chunk_document(
                    text,
                    file_path=filename,
                    chunk_size_tokens=chunk_size_tokens,
                    overlap_sentences=2
                )
                
                if not chunks_data:
                    current_app.logger.warning(f"Нет чанков для {filename}, пропускаем")
                    stats['skipped_empty'] += 1
                    continue
                
                # Удаляем старые чанки и вставляем новые
                with db.db.connect() as conn:
                    with conn.cursor() as cur:
                        # Удаляем старые чанки
                        cur.execute("DELETE FROM chunks WHERE document_id = %s;", (doc_id,))
                        
                        # Вставляем новые чанки
                        for idx, chunk in enumerate(chunks_data):
                            # chunk_document возвращает 'content', а не 'text'
                            chunk_text = chunk.get('content', chunk.get('text', ''))
                            cur.execute("""
                                INSERT INTO chunks (document_id, chunk_idx, text, created_at)
                                VALUES (%s, %s, %s, NOW());
                            """, (doc_id, idx, chunk_text))
                        
                        # Обновляем метаданные документа
                        cur.execute("""
                            UPDATE documents
                            SET indexing_cost_seconds = %s,
                                last_accessed_at = NOW()
                            WHERE id = %s;
                        """, (extract_time, doc_id))
                    conn.commit()
                
                # Обновляем search_index для этого документа
                try:
                    from webapp.db.repositories.search_index_repository import SearchIndexRepository
                    with db.db.connect() as conn:
                        search_repo = SearchIndexRepository(conn)
                        # Удаляем старые записи search_index
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM search_index WHERE document_id = %s;", (doc_id,))
                        conn.commit()
                        
                        # Создаём новые записи для каждого чанка
                        for chunk in chunks_data:
                            chunk_text = chunk.get('content', chunk.get('text', ''))
                            search_repo.add_entry(
                                user_id=owner_id,
                                document_id=doc_id,
                                content=chunk_text,
                                metadata={
                                    'filename': filename,
                                    'file_path': file_path
                                }
                            )
                        conn.commit()
                except Exception as search_err:
                    current_app.logger.warning(f"Ошибка обновления search_index для {filename}: {search_err}")
                
                stats['reindexed'] += 1
                current_app.logger.info(f"Переиндексирован {filename}: {len(chunks_data)} чанков, {extract_time:.2f}с")
                
            except Exception as e:
                current_app.logger.exception(f"Ошибка переиндексации {filename}: {e}")
                stats['errors'] += 1
                continue
        
        # Обновляем root_hash после полной пересборки
        current_root_hash = calculate_root_hash(folder_path)
        if current_root_hash:
            update_folder_index_status(db, owner_id, folder_path, current_root_hash)
        
        message = (
            f"Пересборка завершена: переиндексировано {stats['reindexed']} из {stats['total_docs']} документов, "
            f"пропущено пустых: {stats['skipped_empty']}, ошибок: {stats['errors']}"
        )
        return True, message, stats
        
    except Exception as e:
        current_app.logger.exception("Ошибка полной пересборки индекса")
        return False, str(e), {}
