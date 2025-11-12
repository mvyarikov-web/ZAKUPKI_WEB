#!/usr/bin/env python3
"""
Ручной тест просмотра индекса с реальными документами из БД.
Проверяет полный цикл: БД → /view_index → отображение.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp.db.base import SessionLocal
from webapp.db.models import User, UserDocument, Document, Chunk, SearchIndex


def test_real_documents():
    """Проверка реальных документов в БД."""
    db = SessionLocal()
    
    print("="*80)
    print("ТЕСТ: Проверка документов для admin@localhost")
    print("="*80)
    
    # 1. Проверяем пользователя
    user = db.query(User).filter_by(email='admin@localhost').first()
    if not user:
        print("❌ Пользователь admin@localhost не найден!")
        return False
    
    print(f"\n✅ Пользователь найден:")
    print(f"   ID: {user.id}")
    print(f"   Email: {user.email}")
    print(f"   Role: {user.role}")
    
    # 2. Проверяем документы через user_documents
    user_docs = db.query(UserDocument).filter_by(
        user_id=user.id,
        is_soft_deleted=False
    ).all()
    
    print(f"\n📄 Документов пользователя: {len(user_docs)}")
    
    if len(user_docs) == 0:
        print("❌ У пользователя нет документов!")
        return False
    
    # 3. Проверяем каждый документ
    for i, ud in enumerate(user_docs[:5], 1):  # Первые 5 для краткости
        doc = db.query(Document).filter_by(id=ud.document_id).first()
        if not doc:
            print(f"❌ Документ {ud.document_id} не найден!")
            continue
        
        # Проверяем chunks
        chunks = db.query(Chunk).filter_by(document_id=doc.id).all()
        
        # Проверяем search_index
        search_entries = db.query(SearchIndex).filter_by(
            document_id=doc.id,
            user_id=user.id
        ).all()
        
        print(f"\n{i}. Документ: {ud.original_filename or doc.sha256[:8]}")
        print(f"   Document ID: {doc.id}")
        print(f"   User path: {ud.user_path}")
        print(f"   Blob size: {doc.size_bytes} bytes")
        print(f"   Mime: {doc.mime}")
        print(f"   Chunks: {len(chunks)}")
        print(f"   SearchIndex: {len(search_entries)}")
        
        if chunks:
            total_chars = sum(len(c.text or '') for c in chunks)
            print(f"   Total chars: {total_chars}")
            print(f"   First chunk preview: {chunks[0].text[:100] if chunks[0].text else 'None'}...")
        
        if search_entries:
            print(f"   SearchIndex content length: {len(search_entries[0].content or '')}")
            print(f"   Content preview: {(search_entries[0].content or '')[:100]}...")
    
    db.close()
    
    print("\n" + "="*80)
    print("✅ ТЕСТ ЗАВЕРШЁН: Документы найдены в БД")
    print("="*80)
    return True


def test_view_index_endpoint():
    """Тест эндпоинта /view_index через HTTP."""
    import requests
    
    print("\n" + "="*80)
    print("ТЕСТ: HTTP запрос к /view_index")
    print("="*80)
    
    try:
        response = requests.get('http://127.0.0.1:8081/view_index', timeout=10)
        print(f"\n✅ Статус: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('Content-Type')}")
        print(f"   Content-Length: {len(response.text)} символов")
        
        # Проверяем наличие контента
        content = response.text
        
        # Проверяем HTML-метки документов (реальный формат отображения)
        has_doc_labels = 'index-document-label' in content
        has_doc_headers = 'index-document-header' in content
        has_title_label = 'ЗАГОЛОВОК:' in content
        has_format_label = 'Формат:' in content
        has_source_label = 'Источник:' in content
        
        print(f"\n📊 Анализ содержимого:")
        print(f"   Размер ответа: {len(content)} байт")
        print(f"   Содержит 'index-document-label': {has_doc_labels}")
        print(f"   Содержит 'index-document-header': {has_doc_headers}")
        print(f"   Содержит 'ЗАГОЛОВОК:': {has_title_label}")
        print(f"   Содержит 'Формат:': {has_format_label}")
        print(f"   Содержит 'Источник:': {has_source_label}")
        
        # Подсчитываем количество документов
        doc_count = content.count('index-document-header')
        print(f"   Количество документов: {doc_count}")
        
        # Показываем фрагмент с документом
        import re
        doc_match = re.search(r'<span class="index-document-label">ЗАГОЛОВОК:</span>.*?<span class="index-document-header">(.*?)</span>', content, re.DOTALL)
        if doc_match:
            print(f"\n📄 Пример документа: {doc_match.group(1)[:100]}...")
        
        # Проверки корректности
        if len(content) < 10000:
            print("\n❌ Ответ слишком короткий - возможно индекс пуст!")
            return False
        
        if not has_doc_labels or not has_doc_headers:
            print("\n❌ НЕ НАЙДЕНЫ HTML-метки документов!")
            return False
        
        if doc_count == 0:
            print("\n❌ НЕ НАЙДЕНЫ заголовки документов!")
            return False
        
        if not (has_title_label and has_format_label and has_source_label):
            print("\n❌ НЕ НАЙДЕНЫ метки полей документов!")
            return False
        
        print(f"\n✅ Эндпоинт вернул корректный HTML с {doc_count} документами")
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка при запросе: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_view_index_logic():
    """Тестирует логику формирования view_index напрямую."""
    from webapp.models.rag_models import RAGDatabase
    from webapp.config.config_service import get_config
    
    print("\n" + "="*80)
    print("ТЕСТ: Логика формирования view_index")
    print("="*80)
    
    cfg = get_config()
    dsn = cfg.database_url.replace('postgresql+psycopg2://', 'postgresql://')
    db = RAGDatabase(dsn)
    
    owner_id = 512  # admin@localhost
    
    docs_by_group = {'fast': [], 'medium': [], 'slow': []}
    
    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Запрос как в /view_index
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
                
                print(f"\n✅ Запрос выполнен: {len(rows)} строк")
                
                if len(rows) == 0:
                    print("❌ Запрос не вернул данных!")
                    return False
                
                # Группируем по документам
                current_doc = None
                current_chunks = []
                doc_count = 0
                
                for row in rows:
                    doc_id, filename, storage_url, chunk_idx, text = row
                    
                    if current_doc is None or current_doc['id'] != doc_id:
                        # Сохраняем предыдущий документ
                        if current_doc:
                            current_doc['chunks'] = current_chunks
                            ext = os.path.splitext(filename)[1].lower()
                            if ext in ['.txt', '.csv', '.html', '.htm']:
                                docs_by_group['fast'].append(current_doc)
                            elif ext in ['.docx', '.xlsx', '.xls']:
                                docs_by_group['medium'].append(current_doc)
                            else:
                                docs_by_group['slow'].append(current_doc)
                            doc_count += 1
                        
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
                    doc_count += 1
                
                print(f"\n📊 Результаты группировки:")
                print(f"   Всего документов: {doc_count}")
                print(f"   Fast (TXT/CSV/HTML): {len(docs_by_group['fast'])}")
                print(f"   Medium (DOCX/XLSX): {len(docs_by_group['medium'])}")
                print(f"   Slow (PDF): {len(docs_by_group['slow'])}")
                
                # Показываем первый документ из каждой группы
                for group_name, docs in docs_by_group.items():
                    if docs:
                        doc = docs[0]
                        print(f"\n   {group_name.upper()} - Первый документ:")
                        print(f"      ID: {doc['id']}")
                        print(f"      Filename: {doc['filename']}")
                        print(f"      Chunks: {len(doc.get('chunks', []))}")
                        if doc.get('chunks'):
                            print(f"      First chunk: {doc['chunks'][0]['text'][:100]}...")
                
                if doc_count == 0:
                    print("\n❌ Не найдено ни одного документа!")
                    return False
                
                print("\n✅ Логика формирования индекса работает корректно")
                return True
                
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "="*80)
    print("КОМПЛЕКСНЫЙ ТЕСТ /view_index")
    print("="*80)
    
    # Тест 1: Проверка БД
    result1 = test_real_documents()
    
    # Тест 2: Логика формирования
    result2 = test_view_index_logic()
    
    # Тест 3: HTTP эндпоинт
    result3 = test_view_index_endpoint()
    
    print("\n" + "="*80)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("="*80)
    print(f"1. Проверка БД: {'✅ PASS' if result1 else '❌ FAIL'}")
    print(f"2. Логика формирования: {'✅ PASS' if result2 else '❌ FAIL'}")
    print(f"3. HTTP эндпоинт: {'✅ PASS' if result3 else '❌ FAIL'}")
    print("="*80)
    
    if all([result1, result2, result3]):
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        sys.exit(0)
    else:
        print("\n❌ ЕСТЬ ПРОБЛЕМЫ - см. детали выше")
        sys.exit(1)
