#!/usr/bin/env python3
"""
Скрипт для принудительной переиндексации документов в БД.
Пересоздаёт чанки для всех документов пользователя, которые существуют в глобальном пуле.
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp import create_app
from webapp.models.rag_models import RAGDatabase
from webapp.services.db_indexing import rebuild_all_documents

def main():
    """Переиндексация документов для owner_id=5."""
    app = create_app('testing')
    
    with app.app_context():
        db = RAGDatabase()
        owner_id = 5
        folder_path = app.config['UPLOAD_FOLDER']
        
        print(f"🔄 Начинаем переиндексацию для пользователя {owner_id}")
        print(f"📁 Папка: {folder_path}")
        
        success, message, stats = rebuild_all_documents(
            db, 
            owner_id, 
            folder_path,
            chunk_size_tokens=500,
            chunk_overlap_tokens=50
        )
        
        if success:
            print(f"✅ Успешно: {message}")
            print(f"📊 Статистика: {stats}")
        else:
            print(f"❌ Ошибка: {message}")
            sys.exit(1)

if __name__ == '__main__':
    main()
