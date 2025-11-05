"""Скрипт инициализации PostgreSQL для RAG.

Создаёт необходимые таблицы и расширения для векторного поиска.
"""
import os
import sys

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.models.rag_models import RAGDatabase


def initialize_rag_database(database_url: str):
    """
    Инициализировать базу данных для RAG.
    
    Args:
        database_url: URL подключения к PostgreSQL
    """
    print("=" * 60)
    print("Инициализация базы данных для RAG")
    print("=" * 60)
    
    try:
        print("\n1. Подключение к базе данных...")
        db = RAGDatabase(database_url)
        
        print("   ✓ Подключение установлено")
        
        print("\n2. Создание расширений и таблиц...")
        db.initialize_schema()
        
        print("   ✓ Расширение pgvector установлено")
        print("   ✓ Таблица documents создана")
        print("   ✓ Таблица chunks создана")
        print("   ✓ Индексы созданы")
        
        print("\n3. Проверка статистики...")
        stats = db.get_stats()
        
        print(f"   Документов в базе: {stats['documents']}")
        print(f"   Чанков в базе: {stats['chunks']}")
        
        print("\n" + "=" * 60)
        print("✓ Инициализация завершена успешно!")
        print("=" * 60)
        
        return True
    
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ Ошибка инициализации: {e}")
        print("=" * 60)
        print("\nВозможные причины:")
        print("1. PostgreSQL не запущен")
        print("2. Неверные учётные данные")
        print("3. Расширение pgvector не установлено")
        print("\nДля установки pgvector:")
        print("  - На Ubuntu/Debian: sudo apt-get install postgresql-16-pgvector")
        print("  - На macOS: brew install pgvector")
        print("  - Или через расширение: CREATE EXTENSION vector;")
        
        return False


def main():
    """Основная функция."""
    # Получаем DATABASE_URL из переменных окружения или конфига
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("Ошибка: переменная окружения DATABASE_URL не установлена.")
        print("\nПример:")
        print("  export DATABASE_URL='postgresql://user:password@localhost:5432/zakupki_rag'")
        print("\nИли создайте файл .env с содержимым:")
        print("  DATABASE_URL=postgresql://user:password@localhost:5432/zakupki_rag")
        sys.exit(1)
    
    print(f"DATABASE_URL: {database_url[:30]}...")
    
    success = initialize_rag_database(database_url)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
