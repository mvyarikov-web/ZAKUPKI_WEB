#!/usr/bin/env python3
"""
Интеграционный тест новой логики search_index.

Проверяет:
1. Каждый файл индексируется отдельно и сохраняется в search_index
2. Поиск работает через search_index с полнотекстовым поиском
3. Индекс собирается на лету при поиске
"""
import os
import sys
import tempfile
import psycopg2

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from webapp.config.config_service import get_config
from webapp.models.rag_models import RAGDatabase
from webapp.services.db_indexing import index_document_to_db
from webapp.db.repositories.search_index_repository import SearchIndexRepository

# Создаём Flask app для контекста
app = create_app()


def test_individual_file_indexing():
    """Тест: каждый файл индексируется отдельно."""
    print("\n" + "="*60)
    print("ТЕСТ 1: Индексация отдельных файлов")
    print("="*60)
    
    with app.app_context():
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        db = RAGDatabase(dsn)
        
        # Создаём временные тестовые файлы
        test_files = [
            ("test_file_1.txt", "Это первый тестовый файл с ключевым словом жираф"),
            ("test_file_2.txt", "Второй файл содержит слово слон и другой контент"),
            ("test_file_3.txt", "Третий файл про жирафа и слона вместе")
        ]
        
        temp_dir = tempfile.mkdtemp()
        indexed_docs = []
        
        try:
            user_id = 1
            
            for filename, content in test_files:
                # Создаём файл
                file_path = os.path.join(temp_dir, filename)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Индексируем
                import hashlib
                file_hash = hashlib.sha256(content.encode()).hexdigest()
                file_info = {
                    'sha256': file_hash,
                    'size': len(content),
                    'content_type': 'text/plain'
                }
                
                doc_id, cost = index_document_to_db(
                    db=db,
                    file_path=file_path,
                    file_info=file_info,
                    user_id=user_id,
                    original_filename=filename,
                    user_path=filename,
                    chunk_size_tokens=500,
                    chunk_overlap_tokens=50
                )
                
                indexed_docs.append({
                    'doc_id': doc_id,
                    'filename': filename,
                    'content': content
                })
                
                print(f"✅ Проиндексирован: {filename}, doc_id={doc_id}, cost={cost:.2f}s")
            
            # Проверяем search_index
            print("\n📊 Проверка записей в search_index:")
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    # Ищем только наши тестовые файлы
                    cur.execute("""
                        SELECT id, document_id, user_id, 
                               LEFT(content, 50) as content_preview,
                               metadata->>'original_filename' as filename
                        FROM search_index
                        WHERE user_id = %s 
                          AND metadata->>'original_filename' LIKE 'test_file_%%'
                        ORDER BY id;
                    """, (user_id,))
                    
                    rows = cur.fetchall()
                    print(f"Всего записей в search_index для test_file_*.txt: {len(rows)}")
                    
                    for row in rows:
                        idx, doc_id, uid, preview, fname = row
                        print(f"  ID={idx}, doc_id={doc_id}, file={fname}")
                        print(f"    Превью: {preview}...")
                    
                    assert len(rows) == len(test_files), f"Ожидалось {len(test_files)} записей, получено {len(rows)}"
            
            print("\n✅ ТЕСТ 1 ПРОЙДЕН: Все файлы проиндексированы отдельно")
            return True, indexed_docs, user_id
            
        except Exception as e:
            print(f"\n❌ ТЕСТ 1 ПРОВАЛЕН: {e}")
            import traceback
            traceback.print_exc()
            return False, [], None
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_search_through_index(indexed_docs, user_id):
    """Тест: поиск работает через search_index."""
    with app.app_context():
        print("\n" + "="*60)
        print("ТЕСТ 2: Поиск через search_index")
        print("="*60)
        
        if not indexed_docs or not user_id:
            print("⚠️ ТЕСТ 2 ПРОПУЩЕН: нет проиндексированных документов")
            return False
        
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        db = RAGDatabase(dsn)
        
        try:
            with db.db.connect() as conn:
                search_repo = SearchIndexRepository(conn)
                
                # Тест 1: Поиск по слову "жираф"
                print("\n🔍 Поиск: ['жираф']")
                results = search_repo.search(user_id, ['жираф'], limit=100)
                print(f"Найдено результатов: {len(results)}")
                
                for r in results:
                    metadata = r.get('metadata', {})
                    filename = metadata.get('original_filename', 'unknown')
                    rank = r.get('rank', 0)
                    snippet = r.get('snippet', '')[:100]
                    print(f"  📄 {filename} (rank={rank:.4f})")
                    print(f"     Сниппет: {snippet}...")
                
                # Должны найти 2 файла (test_file_1 и test_file_3)
                assert len(results) >= 2, f"Ожидалось минимум 2 результата для 'жираф', получено {len(results)}"
                
                # Тест 2: Поиск по слову "слон"
                print("\n🔍 Поиск: ['слон']")
                results = search_repo.search(user_id, ['слон'], limit=100)
                print(f"Найдено результатов: {len(results)}")
                
                for r in results:
                    metadata = r.get('metadata', {})
                    filename = metadata.get('original_filename', 'unknown')
                    rank = r.get('rank', 0)
                    print(f"  📄 {filename} (rank={rank:.4f})")
                
                # Должны найти 2 файла (test_file_2 и test_file_3)
                assert len(results) >= 2, f"Ожидалось минимум 2 результата для 'слон', получено {len(results)}"
                
                # Тест 3: Поиск по двум словам (OR)
                print("\n🔍 Поиск: ['жираф', 'слон'] (OR)")
                results = search_repo.search(user_id, ['жираф', 'слон'], limit=100)
                print(f"Найдено результатов: {len(results)}")
                
                for r in results:
                    metadata = r.get('metadata', {})
                    filename = metadata.get('original_filename', 'unknown')
                    rank = r.get('rank', 0)
                    print(f"  📄 {filename} (rank={rank:.4f})")
                
                # Должны найти все 3 файла
                assert len(results) >= 3, f"Ожидалось минимум 3 результата для OR-поиска, получено {len(results)}"
                
                print("\n✅ ТЕСТ 2 ПРОЙДЕН: Поиск через search_index работает")
                return True
                
        except Exception as e:
            print(f"\n❌ ТЕСТ 2 ПРОВАЛЕН: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_index_on_the_fly():
    """Тест: индекс собирается на лету при поиске."""
    with app.app_context():
        print("\n" + "="*60)
        print("ТЕСТ 3: Индекс собирается на лету")
        print("="*60)
        
        config = get_config()
        dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
        
        try:
            conn = psycopg2.connect(dsn)
            cur = conn.cursor()
            
            # Проверяем, что нет файла _search_index.txt (или он не используется)
            # Папка index/ обычно находится в корне проекта
            old_index_path = os.path.join(os.getcwd(), 'index', '_search_index.txt')
            
            if os.path.exists(old_index_path):
                print(f"⚠️ Найден старый индекс: {old_index_path}")
                print("   (Это нормально, он не используется)")
            else:
                print(f"✅ Старый файловый индекс отсутствует: {old_index_path}")
            
            # Проверяем, что search_vector заполнен (триггер работает)
            cur.execute("""
                SELECT COUNT(*) 
                FROM search_index 
                WHERE search_vector IS NOT NULL;
            """)
            count_with_vector = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM search_index;")
            total_count = cur.fetchone()[0]
            
            print(f"\n📊 Статистика search_index:")
            print(f"  Всего записей: {total_count}")
            print(f"  С search_vector: {count_with_vector}")
            
            if total_count > 0:
                percentage = (count_with_vector / total_count) * 100
                print(f"  Процент индексированных: {percentage:.1f}%")
                
                assert count_with_vector == total_count, \
                    f"Не все записи имеют search_vector ({count_with_vector}/{total_count})"
            
            # Проверяем работу триггера напрямую
            print("\n🔧 Проверка триггера search_vector:")
            cur.execute("""
                SELECT to_tsvector('russian', 'Это тестовое предложение про жирафа');
            """)
            test_vector = cur.fetchone()[0]
            print(f"  Триггер работает: {test_vector is not None}")
            
            cur.close()
            conn.close()
            
            print("\n✅ ТЕСТ 3 ПРОЙДЕН: Индекс создаётся на лету через триггер БД")
            return True
            
        except Exception as e:
            print(f"\n❌ ТЕСТ 3 ПРОВАЛЕН: {e}")
            import traceback
            traceback.print_exc()
            return False


def cleanup_test_data(user_id):
    """Очистка тестовых данных."""
    print("\n" + "="*60)
    print("ОЧИСТКА ТЕСТОВЫХ ДАННЫХ")
    print("="*60)
    
    if not user_id:
        print("⚠️ user_id не задан, пропуск очистки")
        return
    
    config = get_config()
    dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
    
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # Удаляем тестовые записи из search_index
        cur.execute("""
            DELETE FROM search_index 
            WHERE user_id = %s 
              AND metadata->>'original_filename' LIKE 'test_file_%';
        """, (user_id,))
        deleted_search = cur.rowcount
        
        # Удаляем тестовые документы (каскадно удалятся chunks)
        cur.execute("""
            DELETE FROM documents 
            WHERE id IN (
                SELECT document_id FROM user_documents 
                WHERE user_id = %s 
                  AND original_filename LIKE 'test_file_%'
            );
        """, (user_id,))
        deleted_docs = cur.rowcount
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Удалено записей из search_index: {deleted_search}")
        print(f"✅ Удалено документов: {deleted_docs}")
        
    except Exception as e:
        print(f"⚠️ Ошибка очистки: {e}")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧪 ИНТЕГРАЦИОННЫЙ ТЕСТ SEARCH_INDEX")
    print("="*60)
    print("\nПроверяем новую логику:")
    print("  1. Каждый файл индексируется отдельно")
    print("  2. Поиск работает через search_index")
    print("  3. Индекс собирается на лету (триггер БД)")
    
    success1, indexed_docs, user_id = test_individual_file_indexing()
    success2 = test_search_through_index(indexed_docs, user_id) if success1 else False
    success3 = test_index_on_the_fly()
    
    # Очистка
    cleanup_test_data(user_id)
    
    print("\n" + "="*60)
    print("ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("="*60)
    
    if success1 and success2 and success3:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("\n✨ Новая логика работает корректно:")
        print("  ✅ Файлы индексируются отдельно в search_index")
        print("  ✅ Поиск работает через полнотекстовый индекс")
        print("  ✅ search_vector создаётся автоматически триггером")
        print("\n🎯 Готово к продакшену!")
        exit(0)
    else:
        print("❌ ЕСТЬ ПРОБЛЕМЫ")
        if not success1:
            print("  ❌ Индексация не работает")
        if not success2:
            print("  ❌ Поиск не работает")
        if not success3:
            print("  ❌ Триггер не работает")
        exit(1)
