#!/usr/bin/env python3
"""
Скрипт для быстрой проверки состояния PostgreSQL БД.
Использование: python3 scripts/check_db_status.py
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# Загружаем .env
load_dotenv(override=True)

def main():
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        print("❌ DATABASE_URL не настроен в .env")
        sys.exit(1)
    
    if 'postgresql' not in db_url:
        print("⚠️  DATABASE_URL указывает не на PostgreSQL")
        print(f"   Текущий URL: {db_url[:50]}...")
    
    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)
        
        print("=" * 60)
        print("📊 СТАТУС БАЗЫ ДАННЫХ")
        print("=" * 60)
        
        # Версия PostgreSQL
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            pg_version = version.split()[1] if 'PostgreSQL' in version else 'Unknown'
            print(f"\n🐘 PostgreSQL: {pg_version}")
            
            # pgvector
            result = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
            row = result.fetchone()
            if row:
                print(f"🧠 pgvector: {row[0]}")
            else:
                print("⚠️  pgvector: не установлен")
            
            # Версия миграции
            try:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                migration = result.fetchone()
                if migration:
                    print(f"🔖 Alembic: {migration[0]}")
                else:
                    print("⚠️  Миграции не применены")
            except Exception:
                print("⚠️  Таблица alembic_version отсутствует")
        
        # Таблицы
        tables = inspector.get_table_names()
        print(f"\n📋 Таблицы ({len(tables)}):")
        for table in sorted(tables):
            # Подсчёт записей
            with engine.connect() as conn:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.fetchone()[0]
                    print(f"   ✅ {table:20s} ({count:4d} записей)")
                except Exception as e:
                    print(f"   ⚠️  {table:20s} (ошибка: {str(e)[:30]})")
        
        # Размер БД
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as size
            """))
            db_size = result.fetchone()[0]
            print(f"\n💾 Размер БД: {db_size}")
        
        print("\n" + "=" * 60)
        print("✅ Проверка завершена успешно")
        print("=" * 60)
        
    except Exception as e:
        print("\n❌ Ошибка подключения к БД:")
        print(f"   {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
