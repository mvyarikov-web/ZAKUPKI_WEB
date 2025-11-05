"""
Миграция промптов из файлов PROMPT/ в БД для пользователя admin (user_id=5).
"""

import sys
from pathlib import Path
from datetime import datetime

# Добавляем корневую папку проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from webapp.db.base import engine, Base  # noqa: E402
from webapp.db.models import Prompt  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def create_prompts_table():
    """Создает таблицу prompts в БД."""
    print("Создаю таблицу prompts...")
    Base.metadata.create_all(engine, tables=[Prompt.__table__])
    print("✅ Таблица prompts создана")


def load_prompts_from_files(user_id: int = 5):
    """Загружает промпты из папки PROMPT/ в БД."""
    prompts_dir = project_root / "PROMPT"
    
    if not prompts_dir.exists():
        print(f"❌ Папка {prompts_dir} не найдена")
        return
    
    # Список файлов для загрузки
    prompt_files = [f for f in prompts_dir.iterdir() if f.suffix == '.txt' and f.name != '.gitkeep']
    
    print(f"\nНайдено {len(prompt_files)} файлов промптов")
    
    with Session(engine) as session:
        # Проверяем, есть ли уже промпты у пользователя
        existing_count = session.query(Prompt).filter_by(user_id=user_id).count()
        if existing_count > 0:
            print(f"⚠️  У пользователя user_id={user_id} уже есть {existing_count} промптов")
            response = input("Удалить существующие и загрузить заново? (y/n): ")
            if response.lower() == 'y':
                session.query(Prompt).filter_by(user_id=user_id).delete()
                session.commit()
                print("✅ Существующие промпты удалены")
            else:
                print("❌ Миграция отменена")
                return
        
        # Загружаем промпты
        loaded = 0
        for prompt_file in prompt_files:
            try:
                # Читаем содержимое файла
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                if not content:
                    print(f"⚠️  Пропускаю пустой файл: {prompt_file.name}")
                    continue
                
                # Создаем имя промпта из имени файла
                name = prompt_file.stem  # без расширения .txt
                
                # Создаем запись в БД
                prompt = Prompt(
                    user_id=user_id,
                    name=name,
                    content=content,
                    is_shared=False,  # По умолчанию не расшарены
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(prompt)
                loaded += 1
                print(f"✅ Загружен: {name} ({len(content)} символов)")
                
            except Exception as e:
                print(f"❌ Ошибка при загрузке {prompt_file.name}: {e}")
        
        # Сохраняем все изменения
        session.commit()
        print(f"\n✅ Загружено {loaded} промптов для пользователя user_id={user_id}")


def verify_migration(user_id: int = 5):
    """Проверяет результат миграции."""
    print("\nПроверка миграции...")
    with Session(engine) as session:
        prompts = session.query(Prompt).filter_by(user_id=user_id).all()
        print(f"✅ Найдено {len(prompts)} промптов в БД:")
        for prompt in prompts[:5]:  # Показываем первые 5
            print(f"  - {prompt.name} ({len(prompt.content)} символов)")
        if len(prompts) > 5:
            print(f"  ... и ещё {len(prompts) - 5}")


if __name__ == '__main__':
    print("=" * 60)
    print("Миграция промптов из PROMPT/ в PostgreSQL")
    print("=" * 60)
    
    # Шаг 1: Создаем таблицу
    create_prompts_table()
    
    # Шаг 2: Загружаем промпты
    load_prompts_from_files(user_id=5)
    
    # Шаг 3: Проверяем
    verify_migration(user_id=5)
    
    print("\n" + "=" * 60)
    print("✅ Миграция завершена!")
    print("=" * 60)
