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
from datetime import datetime
from flask import current_app
from webapp.models.rag_models import RAGDatabase
from webapp.services.chunking import chunk_document


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
                # Получаем sha256 всех файлов владельца в этой папке
                cur.execute("""
                    SELECT original_filename, sha256
                    FROM documents
                    WHERE owner_id = %s AND is_visible = TRUE
                    AND original_filename LIKE %s;
                """, (owner_id, f"{folder_path}%"))
                
                existing_hashes = {row[0]: row[1] for row in cur.fetchall()}
        
        # Сравниваем хеши
        for file_path, file_info in current_files.items():
            existing_hash = existing_hashes.get(file_path)
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
        
        # 2. Читаем и чанкуем файл
        # TODO: здесь нужна интеграция с extractors для извлечения текста
        # Пока упрощённая версия для демонстрации
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            current_app.logger.warning(f'Ошибка чтения {file_path}: {e}')
            content = ""
        
        if not content:
            indexing_cost = time.time() - start_time
            return 0, indexing_cost
        
        # 3. Чанкуем текст
        chunks = chunk_document(
            content,
            file_path=file_path,
            chunk_size_tokens=chunk_size_tokens,
            overlap_sentences=2  # TODO: использовать chunk_overlap_tokens
        )
        
        if not chunks:
            indexing_cost = time.time() - start_time
            return 0, indexing_cost
        
        # 4. Добавляем документ в БД
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO documents (
                        owner_id, original_filename, content_type, size_bytes, sha256,
                        status, uploaded_at, indexed_at, is_visible, access_count, indexing_cost_seconds
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'indexed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE, 0, %s
                    )
                    ON CONFLICT (owner_id, sha256) WHERE is_visible = TRUE
                    DO UPDATE SET
                        original_filename = EXCLUDED.original_filename,
                        indexed_at = CURRENT_TIMESTAMP,
                        indexing_cost_seconds = EXCLUDED.indexing_cost_seconds
                    RETURNING id;
                """, (
                    owner_id,
                    os.path.basename(file_path),
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
            chunk_sha256 = hashlib.sha256(chunk['text'].encode('utf-8')).hexdigest()
            chunk_data.append({
                'document_id': doc_id,
                'owner_id': owner_id,
                'chunk_idx': idx,
                'text': chunk['text'],
                'text_sha256': chunk_sha256,
                'tokens': chunk.get('tokens', 0),
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
                        INSERT INTO chunks (document_id, owner_id, chunk_idx, text, text_sha256, tokens)
                        VALUES %s;
                        """,
                        [(c['document_id'], c['owner_id'], c['chunk_idx'], c['text'], c['text_sha256'], c['tokens']) 
                         for c in chunk_data]
                    )
                conn.commit()
        
        # 6. Финальное обновление indexing_cost_seconds
        indexing_cost = time.time() - start_time
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documents
                    SET indexing_cost_seconds = %s
                    WHERE id = %s;
                """, (indexing_cost, doc_id))
            conn.commit()
        
        current_app.logger.info(f'Документ {file_path} проиндексирован: {len(chunks)} чанков, {indexing_cost:.2f}с')
        return doc_id, indexing_cost
        
    except Exception as e:
        indexing_cost = time.time() - start_time
        current_app.logger.exception(f'Ошибка индексации {file_path}')
        return 0, indexing_cost


def build_db_index(
    db: RAGDatabase,
    owner_id: int,
    folder_path: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50
) -> Tuple[bool, str, Dict[str, int]]:
    """
    Инкрементальная индексация папки в БД.
    
    Алгоритм:
    1. Вычисляем root_hash текущей папки
    2. Сравниваем с сохранённым в folder_index_status
    3. Если совпадает — пропускаем индексацию
    4. Иначе определяем изменённые файлы и индексируем только их
    5. Обновляем folder_index_status
    
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
        
        # 2. Проверяем статус индексации
        status = get_folder_index_status(db, owner_id, folder_path)
        if status and status['root_hash'] == current_root_hash:
            current_app.logger.info(f'Папка {folder_path} не изменилась (root_hash совпадает), пропускаем индексацию')
            return True, 'Индексация не требуется (папка не изменилась)', {}
        
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
