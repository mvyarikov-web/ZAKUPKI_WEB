#!/usr/bin/env python3
"""
Скрипт для создания таблиц логирования в PostgreSQL.

Создаёт:
1. http_request_logs - логи HTTP запросов к API
2. error_logs - логи ошибок и исключений

Запуск:
    python scripts/create_logging_tables.py
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp.db.base import Base, engine
from webapp.db.models import HTTPRequestLog, ErrorLog


def create_logging_tables():
    """Создать таблицы логирования если их нет."""
    
    print("🔧 Создание таблиц логирования...")
    
    # Проверяем соединение
    try:
        with engine.connect() as conn:
            print(f"✅ Подключение к БД установлено: {engine.url}")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False
    
    try:
        # Создаём только таблицы логирования
        HTTPRequestLog.__table__.create(engine, checkfirst=True)
        print("✅ Таблица http_request_logs создана")
        
        ErrorLog.__table__.create(engine, checkfirst=True)
        print("✅ Таблица error_logs создана")
        
        print("\n🎉 Таблицы логирования успешно созданы!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания таблиц: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_table_info():
    """Показать информацию о созданных таблицах."""
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    
    print("\n📊 Информация о таблицах логирования:\n")
    
    for table_name in ['http_request_logs', 'error_logs']:
        if inspector.has_table(table_name):
            print(f"✅ Таблица '{table_name}':")
            columns = inspector.get_columns(table_name)
            for col in columns:
                print(f"   - {col['name']}: {col['type']}")
            
            # Показываем индексы
            indexes = inspector.get_indexes(table_name)
            if indexes:
                print(f"   Индексы:")
                for idx in indexes:
                    print(f"   - {idx['name']}: {idx['column_names']}")
            
            # Показываем количество записей
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                print(f"   📝 Записей: {count}\n")
        else:
            print(f"❌ Таблица '{table_name}' не существует\n")


if __name__ == '__main__':
    print("=" * 60)
    print("СОЗДАНИЕ ТАБЛИЦ ЛОГИРОВАНИЯ")
    print("=" * 60)
    
    success = create_logging_tables()
    
    if success:
        show_table_info()
        print("\n✨ Готово! Теперь можно использовать логирование в БД.")
    else:
        print("\n❌ Не удалось создать таблицы логирования.")
        sys.exit(1)
