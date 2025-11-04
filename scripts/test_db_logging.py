#!/usr/bin/env python3
"""
Скрипт для проверки работы БД логирования.
Подключается к PostgreSQL и показывает последние записи из таблиц логов.
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.db.base import get_db_context
from webapp.db.models import AppLog, HTTPRequestLog, ErrorLog


def test_logging():
    """Проверяет наличие записей в таблицах логирования."""
    print("=" * 60)
    print("Тестирование БД логирования")
    print("=" * 60)
    
    try:
        with get_db_context() as db:
            # 1. Проверяем app_logs
            print("\n1. Таблица app_logs:")
            count = db.query(AppLog).count()
            print(f"   Всего записей: {count}")
            
            if count > 0:
                logs = db.query(AppLog).order_by(AppLog.created_at.desc()).limit(5).all()
                print("   Последние 5 записей:")
                for log in logs:
                    msg = log.message[:50] if log.message else ""
                    print(f"   [{log.level}] {log.component}: {msg}... ({log.created_at})")
            
            # 2. Проверяем http_request_logs
            print("\n2. Таблица http_request_logs:")
            count = db.query(HTTPRequestLog).count()
            print(f"   Всего записей: {count}")
            
            if count > 0:
                logs = db.query(HTTPRequestLog).order_by(HTTPRequestLog.created_at.desc()).limit(5).all()
                print("   Последние 5 запросов:")
                for log in logs:
                    print(f"   {log.method} {log.path} -> {log.response_status} ({log.response_time_ms}ms) at {log.created_at}")
            
            # 3. Проверяем error_logs
            print("\n3. Таблица error_logs:")
            count = db.query(ErrorLog).count()
            print(f"   Всего записей: {count}")
            
            if count > 0:
                logs = db.query(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(5).all()
                print("   Последние 5 ошибок:")
                for log in logs:
                    resolved = "✅" if log.is_resolved else "❌"
                    msg = log.error_message[:50] if log.error_message else ""
                    print(f"   {resolved} [{log.error_type}] {msg}... ({log.component}, {log.created_at})")
        
        print("\n" + "=" * 60)
        print("✅ Тест завершён успешно!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_logging()
