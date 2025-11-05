"""
Прямая проверка подключения к PostgreSQL без webapp импортов.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Загружаем .env напрямую с override=True (игнорируем conftest.py)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path, override=True)

def main():
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL не установлен в .env")
        return False
    
    print(f"🔍 DATABASE_URL: {database_url[:60]}...")
    
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        
        with engine.connect() as conn:
            # Проверяем версию PostgreSQL
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print("✅ PostgreSQL подключение успешно!")
            print(f"📦 Версия: {version[:80]}...")
            
            # Проверяем текущую базу данных
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            print(f"🗄️  База данных: {db_name}")
            
            # Проверяем наличие расширения pgvector
            result = conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            ))
            has_vector = result.fetchone()[0]
            if has_vector:
                print("✅ Расширение pgvector уже установлено")
            else:
                print("⚠️  Расширение pgvector НЕ установлено (будет создано при миграции)")
            
            # Проверяем список таблиц
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"📋 Найдено таблиц: {len(tables)}")
                for table in tables:
                    print(f"   - {table}")
            else:
                print("✅ База данных пустая (готова к миграции)")
                
    except Exception as e:
        print(f"❌ Ошибка подключения: {type(e).__name__}: {e}")
        return False
    
    print("\n✅ Все проверки пройдены!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
