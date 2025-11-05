"""
Скрипт проверки подключения к PostgreSQL.
"""
from webapp.config import get_config
from sqlalchemy import create_engine, text

def main():
    config = get_config()
    print(f"🔍 DATABASE_URL: {config.database_url[:50]}...")
    
    engine = create_engine(config.database_url, pool_pre_ping=True)
    
    try:
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
            
            # Проверяем наличие расширения pgvector (если уже установлено)
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
        print(f"❌ Ошибка подключения: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
