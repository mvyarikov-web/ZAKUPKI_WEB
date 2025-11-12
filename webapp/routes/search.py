"""Blueprint для поиска и индексации."""
import os
import re
import json
import html as htmllib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app, Response, g
from webapp.services.files import allowed_file
from webapp.services.file_search_state_service import FileSearchStateService
# Legacy imports removed: build_db_index, rebuild_all_documents (Блок 10)
# get_folder_index_status оставлен для статусов
from webapp.services.db_indexing import get_folder_index_status
from webapp.models.rag_models import RAGDatabase
from webapp.config.config_service import get_config
from webapp.utils.path_utils import normalize_path
from webapp.db.base import SessionLocal  # SQLAlchemy session для query()

search_bp = Blueprint('search', __name__)


def _get_rag_db() -> RAGDatabase:
    """Получить RAGDatabase (psycopg2 подключение для legacy кода)."""
    if 'rag_db' not in g:
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        g.rag_db = RAGDatabase(dsn)
    return g.rag_db


def _get_db():
    """Получить SQLAlchemy сессию для query() операций."""
    if 'db_session' not in g:
        g.db_session = SessionLocal()
    return g.db_session


def required_user_id() -> int:
    """Строго получить user_id (см. STRICT_USER_ID)."""
    config = get_config()
    strict = config.strict_user_id

    # 1) g.user.id
    try:
        user = getattr(g, 'user', None)
        if user and getattr(user, 'id', None):
            return int(user.id)
    except Exception:
        pass

    # 2) Заголовок
    try:
        uid = request.headers.get('X-User-ID')
        if uid and str(uid).isdigit():
            return int(uid)
    except Exception:
        pass

    if strict:
        raise ValueError('user_id отсутствует (STRICT_USER_ID)')
    return 1


def _fetch_snippet_from_chunk(conn, document_id: int, term: str, context_chars: int = 100) -> tuple[str, int]:
    """Фолбэк: найти первый chunk с термином и вернуть (сниппет, count_in_chunk).

    Args:
        conn: psycopg2 connection
        document_id: ID документа
        term: искомый термин
        context_chars: ширина контекста для _make_snippet

    Returns:
        (snippet, count) или ("", 0), если не найдено
    """
    try:
        with conn.cursor() as cur2:
            cur2.execute(
                """
                SELECT text
                FROM chunks
                WHERE document_id = %s AND text ILIKE %s
                ORDER BY chunk_idx
                LIMIT 1;
                """,
                (document_id, f"%{term}%"),
            )
            row = cur2.fetchone()
            if not row:
                return "", 0
            chunk_text = row[0] or ""
            # Простой подсчёт вхождений подстроки в чанке
            cnt = chunk_text.lower().count(term.lower())
            return _make_snippet(chunk_text, [term], context_chars=context_chars), cnt
    except Exception:
        return "", 0


def _make_snippet(text: str, keywords: list, context_chars: int = 100) -> str:
    """
    Создаёт сниппет с контекстом вокруг первого найденного ключевого слова.
    
    Args:
        text: Исходный текст
        keywords: Список ключевых слов для поиска
        context_chars: Количество символов контекста до и после ключевого слова
        
    Returns:
        Сниппет с контекстом и многоточиями
    """
    text_lower = text.lower()
    
    # Ищем первое вхождение любого ключевого слова
    min_pos = len(text)
    found_keyword = None
    
    for keyword in keywords:
        pos = text_lower.find(keyword.lower())
        if pos != -1 and pos < min_pos:
            min_pos = pos
            found_keyword = keyword
    
    # Если ни одно ключевое слово не найдено, возвращаем начало
    if found_keyword is None:
        return text[:200] + ('...' if len(text) > 200 else '')
    
    # Вычисляем границы сниппета
    start = max(0, min_pos - context_chars)
    end = min(len(text), min_pos + len(found_keyword) + context_chars)
    
    snippet = text[start:end]
    
    # Добавляем многоточия
    if start > 0:
        snippet = '...' + snippet
    if end < len(text):
        snippet = snippet + '...'
    
    return snippet


def _count_term_in_chunks(conn, document_id: int, term: str) -> int:
    """
    Подсчитывает количество вхождений термина во всех chunks документа.
    
    Args:
        conn: Подключение к БД
        document_id: ID документа
        term: Термин для поиска
        
    Returns:
        Количество вхождений термина
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT text FROM chunks
            WHERE document_id = %s
            ORDER BY chunk_idx
        """, (document_id,))
        rows = cur.fetchall()
        
        # Считаем во всех чанках
        total_count = 0
        term_lower = term.lower()
        for row in rows:
            chunk_text = row[0] or ''
            total_count += chunk_text.lower().count(term_lower)
        
        return total_count


def _search_in_db(db: RAGDatabase, owner_id: int, keywords: list, exclude_mode: bool = False) -> list:
    """
    Поиск по search_index с fallback на chunks.
    
    Сначала пытаемся использовать search_index (быстрый полнотекстовый поиск через tsvector).
    Если search_index пуст или произошла ошибка, используем fallback на chunks.
    
    Args:
        db: Подключение к БД
        owner_id: ID владельца
        keywords: Список ключевых слов
        exclude_mode: Если True, ищет файлы БЕЗ ключевых слов
        
    Returns:
        Список результатов поиска
    """
    # Пробуем поиск через search_index (приоритетный метод)
    try:
        from webapp.db.repositories.search_index_repository import SearchIndexRepository
        
        with db.db.connect() as conn:
            search_repo = SearchIndexRepository(conn)
            
            if exclude_mode:
                # Для exclude_mode используем chunks (search_index не поддерживает NOT)
                current_app.logger.info("Exclude mode: используем поиск по chunks")
                return _search_in_chunks(db, owner_id, keywords, exclude_mode=True)
            
            # Полнотекстовый поиск через search_index
            search_results = search_repo.search(owner_id, keywords, limit=500)
            
            if search_results:
                current_app.logger.info(f"Найдено {len(search_results)} результатов через search_index")
                
                # Форматируем результаты для фронтенда
                results = []
                for sr in search_results:
                    metadata = sr.get('metadata', {})
                    filename = metadata.get('original_filename', f"doc_{sr['document_id']}")
                    user_path = metadata.get('user_path', filename)
                    normalized_path = normalize_path(user_path)
                    
                    # Подсчёт совпадений по терминам + корректные пер-термин сниппеты
                    per_term = []
                    content = sr.get('content', '') or ''
                    content_lower = content.lower()
                    for term in keywords:
                        # ВАЖНО: считаем из chunks (полные данные), а не из search_index.content (может быть обрезан)
                        count = _count_term_in_chunks(conn, sr['document_id'], term)
                        
                        if count > 0:
                            # Сниппет формируем из content, если там есть термин
                            if content_lower.count(term.lower()) > 0:
                                per_term.append({
                                    'term': term,
                                    'count': count,
                                    'snippets': [_make_snippet(content, [term], 100)]
                                })
                            else:
                                # Фолбэк: ищем чанк с термином и формируем сниппет оттуда
                                fb_snip, _ = _fetch_snippet_from_chunk(conn, sr['document_id'], term, context_chars=100)
                                per_term.append({
                                    'term': term,
                                    'count': count,
                                    'snippets': [fb_snip if fb_snip else '...']
                                })
                    
                    per_term.sort(key=lambda x: x['count'], reverse=True)
                    
                    results.append({
                        'file': filename,
                        'storage_url': normalized_path,
                        'filename': filename,
                        'source': normalized_path,
                        'path': normalized_path,
                        'matches': [{
                            'chunk_idx': 0,
                            # Для совместимости оставляем общий сниппет, но он не влияет на per_term
                            'snippet': sr.get('snippet', _make_snippet(content, keywords, 100)),
                            'text': content[:200]
                        }],
                        'match_count': sum(pt['count'] for pt in per_term),
                        'doc_id': sr['document_id'],
                        'per_term': per_term,
                        'rank': sr.get('rank', 0.0)
                    })
                
                return results
            else:
                current_app.logger.info("search_index пуст, fallback на поиск по chunks")
                return _search_in_chunks(db, owner_id, keywords, exclude_mode)
                
    except Exception as e:
        current_app.logger.warning(f"Ошибка поиска через search_index: {e}, fallback на chunks")
        return _search_in_chunks(db, owner_id, keywords, exclude_mode)


def _search_in_chunks(db: RAGDatabase, owner_id: int, keywords: list, exclude_mode: bool = False) -> list:
    """
    FALLBACK: Поиск по чанкам в БД через глобальные documents с видимостью через user_documents.
    
    Используется когда search_index недоступен или пуст.
    
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
                if exclude_mode:
                    # Ищем документы, где ни один термин не встречается
                    conditions = []
                    params = [owner_id]
                    for kw in keywords:
                        conditions.append("c.text NOT ILIKE %s")
                        params.append(f'%{kw}%')
                    where_clause = " AND ".join(conditions)
                    cur.execute(f"""
SELECT DISTINCT d.id, COALESCE(ud.original_filename, d.sha256) AS filename
FROM user_documents ud
JOIN documents d ON d.id = ud.document_id
JOIN chunks c ON c.document_id = d.id
WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
  AND {where_clause};
""", params)
                    rows = cur.fetchall()
                    for row in rows:
                        results.append({
                            'file': row[1],
                            'matches': [],
                            'match_count': 0,
                            'status': 'no_match'
                        })
                else:
                    # Обычный поиск по совпадениям
                    conditions = []
                    params = [owner_id]
                    for kw in keywords:
                        conditions.append("c.text ILIKE %s")
                        params.append(f'%{kw}%')
                    where_clause = " OR ".join(conditions)
                    cur.execute(f"""
SELECT 
    d.id,
    COALESCE(ud.original_filename, d.sha256) AS filename,
    ud.user_path,
    c.chunk_idx,
    c.text
FROM user_documents ud
JOIN documents d ON d.id = ud.document_id
JOIN chunks c ON c.document_id = d.id
WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
  AND ({where_clause})
ORDER BY filename, c.chunk_idx
LIMIT 500;
""", params)
                    rows = cur.fetchall()
                    
                    # Группируем по файлам и одновременно собираем per_term
                    file_matches = {}
                    for row in rows:
                        doc_id, filename, storage_url, chunk_idx, text = row
                        
                        # Нормализуем storage_url для согласованности
                        normalized_path = normalize_path(storage_url)
                        
                        if filename not in file_matches:
                            file_matches[filename] = {
                                'file': filename,
                                'storage_url': normalized_path,
                                'filename': filename,   # совместимость для фронта
                                'source': normalized_path,  # ключ группировки в UI
                                'path': normalized_path,    # совместимость
                                'matches': [],
                                'match_count': 0,
                                'doc_id': doc_id,
                                '_per_term': {t: {'count': 0, 'snippets': []} for t in keywords}
                            }
                        
                        # Создаём сниппет с контекстом вокруг ключевого слова
                        snippet = _make_snippet(text, keywords, context_chars=100)
                        
                        file_matches[filename]['matches'].append({
                            'chunk_idx': chunk_idx,
                            'snippet': snippet,
                            'text': text[:200]  # ограничиваем для производительности
                        })
                        file_matches[filename]['match_count'] += 1

                        # Пер-термин статистика для UI (по каждому ключу считаем вхождения и берём до 2 сниппетов)
                        try:
                            lower_text = text.lower()
                            for term in keywords:
                                term_lower = term.lower()
                                # Простой подсчёт подстроки
                                cnt = lower_text.count(term_lower)
                                if cnt > 0:
                                    entry = file_matches[filename]['_per_term'][term]
                                    entry['count'] += cnt
                                    # До двух сниппетов на термин для одного файла
                                    if len(entry['snippets']) < 2:
                                        entry['snippets'].append(_make_snippet(text, [term], context_chars=100))
                        except Exception:
                            # Не ломаем общий поиск из-за проблем подсчёта
                            pass
                    
                    # Преобразуем _per_term в per_term для ответа (убираем термины с 0 совпадений)
                    results = []
                    for fm in file_matches.values():
                        per_term = []
                        for term, data in fm.get('_per_term', {}).items():
                            count = int(data.get('count', 0))
                            # Пропускаем термины с нулевым количеством совпадений
                            if count > 0:
                                per_term.append({
                                    'term': term,
                                    'count': count,
                                    'snippets': data.get('snippets', [])
                                })
                        # Сортируем по убыванию количества
                        per_term.sort(key=lambda x: x['count'], reverse=True)
                        fm['per_term'] = per_term
                        # Убираем служебное поле
                        fm.pop('_per_term', None)
                        results.append(fm)
                    
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



def _get_files_state():
    """Получить экземпляр FileSearchStateService для текущего приложения."""
    # Сервис сам определит путь к файлу из конфига
    return FileSearchStateService()


@search_bp.route('/search', methods=['POST'])
def search():
    """Поиск по ключевым словам (спецификация 015).
    
    Поиск всегда происходит в БД с фильтрацией по user_documents (user_id, is_soft_deleted=FALSE).
    Legacy файловый индекс больше не поддерживается.
    """
    search_terms = request.json.get('search_terms', '')
    exclude_mode = request.json.get('exclude_mode', False)
    
    # Поддержка и списка и строки
    if isinstance(search_terms, list):
        raw_terms = [str(t).strip() for t in search_terms if str(t).strip()]
    elif isinstance(search_terms, str):
        if not search_terms.strip():
            return jsonify({'error': 'Введите ключевые слова для поиска'}), 400
        raw_terms = [t.strip() for t in search_terms.split(',') if t.strip()]
    else:
        return jsonify({'error': 'Неверный формат search_terms (ожидается строка или массив)'}), 400
    
    if not raw_terms:
        return jsonify({'error': 'Введите ключевые слова для поиска'}), 400
    
    # Валидация: не более 10 терминов, длина 2..64, удаление дубликатов
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
    
    rag_db = _get_rag_db()  # Используем RAGDatabase для поиска
    try:
        owner_id = required_user_id()
    except ValueError:
        return jsonify({'error': 'Не указан идентификатор пользователя (X-User-ID)'}), 400
    
    try:
        # Поиск с фильтрацией по owner_id и is_visible=TRUE
        results = _search_in_db(rag_db, owner_id, filtered, exclude_mode)
        
        # Логируем пути для отладки
        if results:
            sample_paths = [r.get('source', 'N/A') for r in results[:3]]
            current_app.logger.debug(f"Примеры путей в результатах поиска: {sample_paths}")
        
        # Обновляем метрики использования (access_count, last_accessed_at)
        _update_document_access_metrics(rag_db, results)
        
        # Сохраняем последние поисковые термины для UI (/ и /view_index)
        try:
            files_state = _get_files_state()
            files_state.set_last_search_terms(','.join(filtered))
        except Exception:
            current_app.logger.debug('Не удалось сохранить последние поисковые термины', exc_info=True)
        
        current_app.logger.info(f"Поиск в БД завершён: найдено {len(results)} результатов")
        return jsonify({'results': results})
        
    except Exception as e:
        current_app.logger.exception("Ошибка поиска в БД")
        return jsonify({'error': f'Ошибка поиска: {str(e)}'}), 500


# Удалено: парсинг файлового индекса (_search_index.txt) — legacy


@search_bp.route('/build_index', methods=['POST'])
def build_index_route():
    """Переиндексация всех документов пользователя из БД. ИНКРЕМЕНТ 020 - Блок 9.
    
    Читает все документы пользователя из user_documents,
    извлекает текст из blob и пересоздаёт chunks.
    """
    config = get_config()
    
    try:
        current_app.logger.info("Запуск переиндексации из БД (increment-020, Блок 9)")
        
        db = _get_db()  # SQLAlchemy session
        rag_db = _get_rag_db()  # RAGDatabase для index_document_to_db
        try:
            owner_id = required_user_id()
        except ValueError:
            return jsonify({'success': False, 'message': 'Не указан идентификатор пользователя (X-User-ID)'}), 400
        
        # Получаем параметр force_rebuild из JSON-запроса (по умолчанию True)
        force_rebuild = request.json.get('force_rebuild', True) if request.is_json else True
        
        from webapp.db.models import Document, UserDocument, Chunk
        from webapp.services.db_indexing import index_document_to_db
        from sqlalchemy import and_
        
        # Получаем все не удалённые документы пользователя (через SQLAlchemy)
        results = db.query(UserDocument, Document).join(
            Document, Document.id == UserDocument.document_id
        ).filter(
            and_(
                UserDocument.user_id == owner_id,
                UserDocument.is_soft_deleted == False
            )
        ).all()
        
        stats = {
            'total_docs': len(results),
            'reindexed': 0,
            'skipped_empty': 0,
            'errors': 0
        }
        
        current_app.logger.info(f"Найдено {len(results)} документов для переиндексации user_id={owner_id}")
        
        for user_doc, document in results:
            if not document.blob:
                current_app.logger.warning(f"Документ {document.id} без blob, пропускаем")
                stats['skipped_empty'] += 1
                continue
            
            try:
                # Если force_rebuild=True, удаляем существующие chunks и search_index
                if force_rebuild:
                    from webapp.db.models import SearchIndex
                    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
                    db.query(SearchIndex).filter(SearchIndex.document_id == document.id).delete()
                    db.commit()
                    current_app.logger.info(f"Удалены старые chunks и search_index для документа {document.id}")
                
                file_info = {
                    'sha256': document.sha256,
                    'size': document.size_bytes,
                    'content_type': document.mime or 'application/octet-stream'
                }
                
                doc_id, indexing_cost = index_document_to_db(
                    db=rag_db,  # RAGDatabase для индексации
                    file_path="",  # Пустой путь - чтение из blob
                    file_info=file_info,
                    user_id=owner_id,
                    original_filename=user_doc.original_filename or 'document',
                    user_path=user_doc.user_path or user_doc.original_filename,
                    chunk_size_tokens=config.chunk_size_tokens,
                    chunk_overlap_tokens=config.chunk_overlap_tokens
                )
                
                stats['reindexed'] += 1
                current_app.logger.info(f"Переиндексирован doc#{doc_id} ({indexing_cost:.3f}s)")
                
            except Exception as e:
                current_app.logger.exception(f"Ошибка переиндексации документа {document.id}: {e}")
                stats['errors'] += 1
        
        message = f"Переиндексировано {stats['reindexed']}/{stats['total_docs']} документов"
        if stats['errors'] > 0:
            message += f", ошибок: {stats['errors']}"
        
        current_app.logger.info(f"Переиндексация завершена: {message}")
        return jsonify({
            'success': True,
            'message': message,
            'stats': stats
        })
        
    except Exception as e:
        current_app.logger.exception("Ошибка при переиндексации")
        return jsonify({'success': False, 'message': str(e)}), 500


@search_bp.post('/rebuild_index')
def rebuild_index_route():
    """Принудительная пересборка индекса из БД (аналогично /build_index). ИНКРЕМЕНТ 020 - Блок 10.
    
    Извлекает текст заново из blob и перезаписывает chunks в БД.
    """
    try:
        db = _get_db()  # SQLAlchemy session
        rag_db = _get_rag_db()  # RAGDatabase для index_document_to_db
        try:
            owner_id = required_user_id()
        except ValueError:
            return jsonify({'success': False, 'message': 'Не указан идентификатор пользователя (X-User-ID)'}), 400
        
        config = get_config()
        
        current_app.logger.info(f"Запуск принудительной пересборки индекса для user_id={owner_id}")
        
        from webapp.db.models import Document, UserDocument, Chunk
        from webapp.services.db_indexing import index_document_to_db
        from sqlalchemy import and_
        
        # Получаем все не удалённые документы пользователя (через SQLAlchemy)
        results = db.query(UserDocument, Document).join(
            Document, Document.id == UserDocument.document_id
        ).filter(
            and_(
                UserDocument.user_id == owner_id,
                UserDocument.is_soft_deleted == False
            )
        ).all()
        
        stats = {
            'total_docs': len(results),
            'reindexed': 0,
            'skipped_empty': 0,
            'errors': 0
        }
        
        current_app.logger.info(f"Найдено {len(results)} документов для пересборки user_id={owner_id}")
        
        for user_doc, document in results:
            if not document.blob:
                current_app.logger.warning(f"Документ {document.id} без blob, пропускаем")
                stats['skipped_empty'] += 1
                continue
            
            try:
                # Удаляем существующие chunks (принудительная пересборка)
                db.query(Chunk).filter(Chunk.document_id == document.id).delete()
                db.commit()
                
                file_info = {
                    'sha256': document.sha256,
                    'size': document.size_bytes,
                    'content_type': document.mime or 'application/octet-stream'
                }
                
                doc_id, indexing_cost = index_document_to_db(
                    db=rag_db,  # RAGDatabase для индексации
                    file_path="",  # Пустой путь - чтение из blob
                    file_info=file_info,
                    user_id=owner_id,
                    original_filename=user_doc.original_filename or 'document',
                    user_path=user_doc.user_path or user_doc.original_filename,
                    chunk_size_tokens=config.chunk_size_tokens,
                    chunk_overlap_tokens=config.chunk_overlap_tokens
                )
                
                stats['reindexed'] += 1
                current_app.logger.info(f"Пересобран doc#{doc_id} ({indexing_cost:.3f}s)")
                
            except Exception as e:
                current_app.logger.exception(f"Ошибка пересборки документа {document.id}: {e}")
                stats['errors'] += 1
        
        message = f"Пересобрано {stats['reindexed']}/{stats['total_docs']} документов"
        if stats['errors'] > 0:
            message += f", ошибок: {stats['errors']}"
        
        current_app.logger.info(f"Пересборка завершена: {message}")
        return jsonify({
            'success': True,
            'message': message,
            'stats': stats
        })
        
    except Exception as e:
        current_app.logger.exception("Ошибка при пересборке индекса")
        return jsonify({'success': False, 'message': str(e)}), 500


@search_bp.get('/index_status')
def index_status():
    """Возвращает статус индексации и информацию о группах.
    
    Returns:
        JSON с полями:
        - status: idle | running | completed | error
        - group_status: {fast: pending|running|completed, medium: ..., slow: ...}
        - current_group: fast | medium | slow (если running)
        - index_exists: bool (наличие видимых документов для пользователя)
        - index_size: int (байты) — legacy поле (может быть опущено)
        - groups_info: {fast: {files: int, completed: bool}, ...} — статистика групп из progress.json
    """
    try:
        # 1) Телеметрия прогресса (legacy status.json для UI)
        index_folder = current_app.config.get('INDEX_FOLDER')
        status_json_path = os.path.join(index_folder, 'status.json') if index_folder else None
        progress_data = None
        if status_json_path and os.path.exists(status_json_path):
            try:
                with open(status_json_path, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
            except Exception as e:
                current_app.logger.debug('Не удалось прочитать status.json: %s', e)

        # Получаем user_id
        try:
            owner_id = required_user_id()
        except ValueError:
            return jsonify({'error': 'Не указан идентификатор пользователя (X-User-ID)'}), 400

        # 2) DB MODE: Проверяем наличие документов пользователя в БД
        db = _get_db()
        from webapp.db.models import UserDocument
        has_files = False
        try:
            count = db.query(UserDocument).filter_by(
                user_id=owner_id,
                is_soft_deleted=False
            ).count()
            has_files = count > 0
        except Exception as e:
            current_app.logger.debug('Не удалось проверить наличие документов в БД: %s', e)

        # Если нет документов — индекса как такового быть не может
        if not has_files:
            resp = {'exists': False, 'index_exists': False, 'status': 'idle'}
            if progress_data:
                resp['progress'] = progress_data
                # Совместимость: отдаём group_status/group_times, если есть
                if isinstance(progress_data, dict):
                    if 'group_status' in progress_data:
                        resp['group_status'] = progress_data.get('group_status')
                    if 'group_times' in progress_data:
                        resp['group_times'] = progress_data.get('group_times')
            return jsonify(resp)

        # 3) Статус из БД (increment-015): uploads как tracked folder
        # db и owner_id уже получены выше
        try:
            # DB MODE: folder_path больше не используется (все файлы в БД)
            db_status = get_folder_index_status(db, owner_id, "")
        except Exception:
            current_app.logger.debug('Не удалось получить статус из БД для /index_status', exc_info=True)
            db_status = None

        # 4) Количество документов, доступных пользователю (через user_documents)
        docs_count = 0
        try:
            from webapp.db.models import UserDocument
            docs_count = db.query(UserDocument).filter_by(
                user_id=owner_id,
                is_soft_deleted=False
            ).count()
        except Exception as e:
            current_app.logger.debug(f'Не удалось подсчитать документы пользователя: {e}')
            docs_count = 0

        # 5) Формируем ответ (DB-first) с совместимостью полей
        response = {
            'exists': docs_count > 0,
            'index_exists': docs_count > 0,  # совместимость с legacy тестами
            'entries': docs_count,           # map на количество документов в БД
            'db': {
                'documents': docs_count,
                'last_indexed_at': (db_status or {}).get('last_indexed_at').isoformat() if (db_status and db_status.get('last_indexed_at')) else None,
                'root_hash': (db_status or {}).get('root_hash')
            }
        }

        # 6) Включаем статусы групп и времена, если доступны в progress.json
        if progress_data and isinstance(progress_data, dict):
            response['progress'] = progress_data
            response['status'] = progress_data.get('status', 'completed' if docs_count > 0 else 'idle')
            if 'group_status' in progress_data:
                response['group_status'] = progress_data.get('group_status')
            if 'current_group' in progress_data:
                response['current_group'] = progress_data.get('current_group')
            if 'group_times' in progress_data:
                response['group_times'] = progress_data.get('group_times')
        else:
            # Если нет progress.json — просто отражаем факт наличия документов
            response['status'] = 'completed' if docs_count > 0 else 'idle'

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
    # DB MODE: Диагностический просмотр статуса индексации из БД
    try:
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
        
        # DB-first: формируем структуру документов из БД
        from webapp.models.rag_models import RAGDatabase
        from webapp.config.config_service import get_config as _gc
        cfg = _gc()
        dsn = cfg.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        db = RAGDatabase(dsn)
        
        try:
            owner_id = required_user_id()
        except ValueError:
            # Fallback: для просмотра индекса позволяем owner_id=512 (admin@localhost), чтобы не был пустой экран
            owner_id = 512
    
    # Загружаем все документы и их чанки для текущего пользователя через user_documents
        docs_by_group = {'fast': [], 'medium': [], 'slow': []}
        try:
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    # Получаем документы с их чанками
                    cur.execute("""
                        SELECT 
                            d.id,
                            COALESCE(ud.original_filename, d.sha256) AS filename,
                            ud.user_path,
                            c.chunk_idx,
                            c.text
                        FROM user_documents ud
                        JOIN documents d ON d.id = ud.document_id
                        LEFT JOIN chunks c ON c.document_id = d.id
                        WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
                        ORDER BY filename, c.chunk_idx;
                    """, (owner_id,))
                    rows = cur.fetchall()
                    
                    # Группируем по документам
                    current_doc = None
                    current_chunks = []
                    for row in rows:
                        doc_id, filename, storage_url, chunk_idx, text = row
                        
                        if current_doc is None or current_doc['id'] != doc_id:
                            # Сохраняем предыдущий документ
                            if current_doc:
                                current_doc['chunks'] = current_chunks
                                # Определяем группу по расширению (упрощённо)
                                ext = os.path.splitext(filename)[1].lower()
                                if ext in ['.txt', '.csv', '.html', '.htm']:
                                    docs_by_group['fast'].append(current_doc)
                                elif ext in ['.docx', '.xlsx', '.xls']:
                                    docs_by_group['medium'].append(current_doc)
                                else:
                                    docs_by_group['slow'].append(current_doc)
                            
                            # Начинаем новый документ
                            current_doc = {
                                'id': doc_id,
                                'filename': filename,
                                'storage_url': storage_url
                            }
                            current_chunks = []
                        
                        # Добавляем чанк
                        if text:
                            current_chunks.append({
                                'idx': chunk_idx,
                                'text': text,
                                'char_count': len(text)
                            })
                    
                    # Не забываем последний документ
                    if current_doc:
                        current_doc['chunks'] = current_chunks
                        ext = os.path.splitext(current_doc['filename'])[1].lower()
                        if ext in ['.txt', '.csv', '.html', '.htm']:
                            docs_by_group['fast'].append(current_doc)
                        elif ext in ['.docx', '.xlsx', '.xls']:
                            docs_by_group['medium'].append(current_doc)
                        else:
                            docs_by_group['slow'].append(current_doc)
                            
        except Exception as e:
            current_app.logger.exception('Ошибка загрузки документов из БД для view_index')
            # Продолжаем с пустыми группами
        
        # Собираем текстовое представление с документами
        parts = []
        for g in ['fast', 'medium', 'slow']:
            docs = docs_by_group.get(g, [])
            parts.append('')
            parts.append('═' * 80)
            parts.append(f"[ГРУППА: {g.upper()}] {group_labels[g]}")
            status_text = map_status(grp_status.get(g)) if grp_status else 'ожидание'
            parts.append(f"Файлов: {len(docs)} | Статус: {status_text}")
            parts.append('═' * 80)
            parts.append(f"<!-- BEGIN_{g.upper()} -->")
            
            # Добавляем документы
            for doc in docs:
                parts.append('')
                parts.append(f"__LABEL__ЗАГОЛОВОК:__/LABEL__ __HEADER__{doc['filename']}__/HEADER__")
                parts.append(f"__LABEL__Формат:__/LABEL__ {os.path.splitext(doc['filename'])[1]}")
                parts.append(f"__LABEL__Источник:__/LABEL__ {doc.get('storage_url', 'unknown')}")
                
                # Подсчёт символов из чанков
                total_chars = sum(c.get('char_count', 0) for c in doc.get('chunks', []))
                parts.append(f"__LABEL__Символов:__/LABEL__ {total_chars}")
                parts.append('')
                
                # Объединяем тексты чанков
                for chunk in doc.get('chunks', []):
                    if chunk.get('text'):
                        parts.append(chunk['text'])
                        parts.append('')  # разделитель между чанками
                
                # 3 пустые строки между документами
                parts.append('')
                parts.append('')
                parts.append('')
            
            parts.append(f"<!-- END_{g.upper()} -->")
            parts.append('')
        
        content = "\n".join(parts)
        
        # Добавляем метаинформацию в начало
        metadata = [
            "# Диагностический просмотр индекса (DB-first)",
            f"# Обновлён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "#",
            "# Группы: FAST (TXT,CSV,HTML) → MEDIUM (DOCX,XLSX,PDF) → SLOW (OCR)",
            "#",
            ""
        ]
        # DB-first сводка (increment-015): документы и статус папки
        try:
            db = _get_db()
            try:
                owner_id = required_user_id()
            except ValueError:
                owner_id = None
            # Количество документов (видимых пользователю)
            docs_count = None
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM user_documents
                        WHERE user_id = %s AND is_soft_deleted = FALSE;
                        """,
                        (owner_id,)
                    )
                    row = cur.fetchone()
                    docs_count = row[0] if row else None
            # folder_index_status
            db_status = None
            try:
                # DB MODE: folder_path больше не используется
                db_status = get_folder_index_status(db, owner_id, "")
            except Exception:
                db_status = None
            last_idx = db_status.get('last_indexed_at').strftime('%Y-%m-%d %H:%M:%S') if (db_status and db_status.get('last_indexed_at')) else '—'
            root_hash = db_status.get('root_hash') if db_status else '—'
            metadata.extend([
                "# БД-сводка:",
                f"# Документов: {docs_count if docs_count is not None else '—'}",
                f"# Последняя индексация: {last_idx}",
                f"# Root hash (uploads): {root_hash}",
                "#",
                ""
            ])
        except Exception:
            # Не мешаем отображению при сбое БД
            pass
        
        # Примечание: подробная статистика групп доступна через /index_status
        
        metadata.append("#\n" + "=" * 80 + "\n")
        
        # Режим отображения и подсветка
        show_raw = request.args.get('raw', '0') == '1'
        q = request.args.get('q') or ''
        
        # Если не передан параметр q, пытаемся взять термины из последнего поиска
        # Больше НЕ используем автоматически last_search_terms — подсветка только если явно передан q
        
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

        # Обработка плейсхолдеров: всегда конвертируем __LABEL__/__HEADER__ в HTML
        safe = base_text
        placeholders = {}
        counter = 0
        
        # Сохраняем метки через плейсхолдеры (до экранирования HTML)
        for match in re.finditer(r"__LABEL__(.*?)__/LABEL__", safe):
            placeholder = f"__PH_LABEL_{counter}__"
            # Экранируем содержимое метки
            content = htmllib.escape(match.group(1))
            placeholders[placeholder] = f'<span class="index-document-label">{content}</span>'
            safe = safe.replace(match.group(0), placeholder, 1)
            counter += 1
        
        for match in re.finditer(r"__HEADER__(.*?)__/HEADER__", safe):
            placeholder = f"__PH_HEADER_{counter}__"
            # Экранируем содержимое заголовка
            content = htmllib.escape(match.group(1))
            placeholders[placeholder] = f'<span class="index-document-header">{content}</span>'
            safe = safe.replace(match.group(0), placeholder, 1)
            counter += 1
        
        # Экранируем всё остальное
        safe = htmllib.escape(safe)
        
        # Восстанавливаем плейсхолдеры с уже готовыми span-тегами
        for placeholder, original in placeholders.items():
            safe = safe.replace(placeholder, original)
        
        # Если нет терминов поиска — отдаём без подсветки
        if not terms:
            html_page = (
                "<!DOCTYPE html>\n"
                "<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
                "<title>Индекс (БД)</title>\n"
                "<style>body{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;padding:16px;}"
                "pre{white-space:pre-wrap;word-wrap:break-word;background:#f8f8f8;padding:12px;border-radius:6px;}"
                ".index-document-header{color:#2196F3 !important;font-weight:bold;}"
                ".index-document-label{color:#1976D2 !important;font-weight:600;}"
                "a.btn{display:inline-block;margin-bottom:12px;text-decoration:none;background:#3498db;color:#fff;padding:6px 10px;border-radius:4px;margin-right:8px;}"
                "</style>\n"
                "</head><body>\n"
                f"<div><a class=\"btn\" href=\"/\">← На главную</a></div>"
                "<pre>" + safe + "</pre>\n"
                "</body></html>\n"
            )
            return Response(html_page, mimetype='text/html; charset=utf-8')
        
        # Применяем подсветку для терминов поиска
        highlighted = safe
        for term in terms:
            if not term:
                continue
            try:
                # Используем границы слов \b для поиска целых слов и их форм
                # re.escape защищает от спецсимволов, а \b ищет границы слов
                pattern = re.compile(r'\b' + re.escape(term) + r'\w*\b', re.IGNORECASE)
                highlighted = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", highlighted)
            except re.error:
                # Игнорируем некорректный паттерн
                continue

        # Формируем параметры для кнопки переключения режима
        from urllib.parse import quote
        q_param = f"&q={quote(q)}" if q else ""
        toggle_text = "Показать с подсветкой" if show_raw else "Показать полную структуру"
        toggle_raw = '0' if show_raw else '1'
        
        html_page = (
            "<!DOCTYPE html>\n"
            "<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<title>Индекс (БД) — подсветка</title>\n"
            "<style>body{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;padding:16px;}"
            "pre{white-space:pre-wrap;word-wrap:break-word;background:#f8f8f8;padding:12px;border-radius:6px;}"
            "mark{background:#ffeb3b;padding:0 2px;border-radius:2px;}"
            ".index-document-header{color:#2196F3 !important;font-weight:bold;}"
            ".index-document-label{color:#1976D2 !important;font-weight:600;}"
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
