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


# ============================================================================
# [DEPRECATED - ИНКРЕМЕНТ 020, Блок 10]
# Функции calculate_file_hash() и calculate_root_hash() удалены.
# Хеширование теперь происходит в BlobStorageService.calculate_sha256()
# при сохранении файла в blob. Файловая система больше не используется.
# ============================================================================


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



# ============================================================================
# DEPRECATED: update_folder_index_status() — legacy функция для обновления folder_index_status
# Работала с таблицей folder_index_status (root_hash для обнаружения изменений ФС).
# Архитектура изменена (Блок 9): индексация через blob, инкрементальность не нужна.
# ============================================================================


# ============================================================================
# DEPRECATED: find_changed_files() — legacy функция для обнаружения изменённых файлов
# Сравнивала SHA256 файлов на диске с БД для инкрементальной индексации.
# Архитектура изменена (Блок 9): индексация только при загрузке, файлы в blob.
# ============================================================================


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
    """Индексирует документ в БД ТОЛЬКО ИЗ BLOB (инкремент 020, Блок 9).
    
    ⚠️ АРХИТЕКТУРА ПОСЛЕ ИНКРЕМЕНТА 020:
    - Текст извлекается ТОЛЬКО из documents.blob
    - file_path игнорируется (передавайте пустую строку "")
    - Если blob отсутствует → ValueError (индексация невозможна)
    - Дедупликация по file_info['sha256']
    
    Args:
        db: экземпляр RAGDatabase
        file_path: ИГНОРИРУЕТСЯ (backward compatibility, передавайте "")
        file_info: метаданные файла (sha256, size, content_type...)
        user_id: ID пользователя
        original_filename: исходное имя файла
        user_path: путь пользователя для отображения в UI
        chunk_size_tokens: размер чанка в токенах
        chunk_overlap_tokens: перекрытие между чанками (TODO)
    
    Returns:
        (document_id, indexing_cost_seconds)
    
    Raises:
        ValueError: если blob отсутствует в БД
```
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
        
        # 2. Извлекаем текст ТОЛЬКО из blob (NO FILESYSTEM)
        content = ""
        
        if not document_blob:
            # КРИТИЧЕСКАЯ ОШИБКА: blob обязателен после инкремента 020
            error_msg = f'[EXTRACT] ОШИБКА: blob отсутствует для документа SHA256={file_info["sha256"]}, индексация невозможна'
            current_app.logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # Читаем из blob (преобразуем memoryview в bytes)
            blob_bytes = bytes(document_blob) if not isinstance(document_blob, bytes) else document_blob
            current_app.logger.info(f'[EXTRACT] Извлечение текста из blob, размер: {len(blob_bytes)} байт')
            ext = os.path.splitext(original_filename)[1].lower().lstrip('.')
            content = extract_text_from_bytes(blob_bytes, ext) or ""
            current_app.logger.info(f'[EXTRACT] extract_text_from_bytes вернул {len(content)} символов')
        except Exception as e:
            current_app.logger.exception(f'Ошибка извлечения текста из blob {original_filename}: {e}')
            raise
        
        if not content:
            # Graceful degrade: создаём осмысленный placeholder, чтобы PDF не выглядел "пустым"
            ext = os.path.splitext(original_filename)[1].lower()
            if ext == '.pdf':
                content = f'[ПУСТОЙ PDF ИЛИ ОШИБКА ИЗВЛЕЧЕНИЯ] {original_filename}'
            else:
                content = original_filename
        
    # 3. Чанкуем текст
        current_app.logger.info(f'[CHUNK] Начинаем чанкование для {original_filename}, size_tokens={chunk_size_tokens}')
        chunks = chunk_document(
            content,
            file_path=original_filename,  # Используем имя файла вместо пути
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


# ============================================================================
# [DEPRECATED - ИНКРЕМЕНТ 020, Блок 10]
# Функция build_db_index() удалена.
# Индексация теперь происходит автоматически при загрузке файлов в blob
# через BlobStorageService.save_file_to_db() + index_document_to_db().
# Для переиндексации используйте endpoint /build_index, который работает
# с документами из БД (без сканирования папок).
# ============================================================================


# ============================================================================
# DEPRECATED: build_db_index() — legacy функция со сканированием ФС (os.walk)
# Архитектура изменена (Блок 9): все операции через blob storage.
# Индексация теперь выполняется через /build_index → index_document_to_db() с чтением из blob.
# ============================================================================


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


# ============================================================================
# DEPRECATED: handle_duplicate_upload() — legacy функция со сканированием ФС
# Вызывала calculate_file_hash() и работала с os.path
# Архитектура изменена (Блок 9): дедупликация через BlobStorageService.
# Эндпоинт /upload теперь проверяет существование документа по SHA256 через blob.
# ============================================================================


# ============================================================================
# DEPRECATED: rebuild_all_documents() — legacy функция с os.walk() и calculate_file_hash()
# Архитектура изменена (Блок 9): пересборка через /rebuild_index → чтение из blob.
# См. routes/search.py:/rebuild_index для актуальной реализации.
# ============================================================================

