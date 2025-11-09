#!/usr/bin/env python3
"""
Скрипт миграции состояний файлов из search_results.json в БД.

Использование:
    python scripts/migrate_search_states_to_db.py [--dry-run] [--user-id USER_ID]
    
Опции:
    --dry-run       Только показать, что будет мигрировано, без изменений в БД
    --user-id ID    ID пользователя (обязательно для миграции в multi-user окружении)
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_states_from_file(file_path: str) -> dict:
    """Загрузить состояния из JSON файла."""
    if not os.path.exists(file_path):
        logger.warning(f"Файл {file_path} не найден")
        return {
            'last_updated': '',
            'file_status': {},
            'last_search_terms': ''
        }
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


def migrate_states_to_db(states_data: dict, user_id: int, dry_run: bool = False) -> bool:
    """
    Мигрировать состояния файлов в БД.
    
    Args:
        states_data: Данные из search_results.json
        user_id: ID пользователя, которому принадлежат данные
        dry_run: Если True, только показать что будет сделано
    
    Returns:
        True если успешно, False при ошибке
    """
    from webapp.db import get_db
    from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
    
    file_status = states_data.get('file_status', {})
    last_search_terms = states_data.get('last_search_terms', '')
    
    if not file_status:
        logger.warning("Нет состояний файлов для миграции")
        return False
    
    logger.info(f"Найдено файлов для миграции: {len(file_status)}")
    logger.info(f"Последние поисковые термины: {last_search_terms or '(пусто)'}")
    
    if dry_run:
        logger.info("\n=== DRY RUN MODE: Состояния, которые будут мигрированы ===")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Всего файлов: {len(file_status)}")
        
        # Группируем по статусам
        by_status = {}
        for file_path, data in file_status.items():
            status = data.get('status', 'not_checked')
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(file_path)
        
        logger.info("\nРаспределение по статусам:")
        for status, files in sorted(by_status.items()):
            logger.info(f"  {status}: {len(files)} файлов")
            for file_path in files[:5]:  # Показываем первые 5
                logger.info(f"    - {file_path}")
            if len(files) > 5:
                logger.info(f"    ... и ещё {len(files) - 5}")
        
        logger.info(f"\nПоисковые термины: {last_search_terms}")
        logger.info("\n=== Миграция не выполнена (dry-run режим) ===")
        return True
    
    # Реальная миграция
    try:
        db = next(get_db())
        try:
            repo = FileSearchStateRepository(db)
            
            # Создаём таблицу если её нет
            try:
                from webapp.db.models import FileSearchState
                bind = db.get_bind()
                FileSearchState.__table__.create(bind=bind, checkfirst=True)
                logger.info("Таблица file_search_state проверена/создана")
            except Exception as e:
                logger.warning(f"Не удалось создать таблицу: {e}")
            
            # Импортируем состояния
            logger.info(f"Начинаем импорт состояний для user_id={user_id}...")
            repo.from_legacy_format(user_id, states_data)
            
            logger.info(f"✅ Успешно мигрировано {len(file_status)} состояний файлов")
            
            # Проверяем результат
            migrated = repo.get_user_states(user_id)
            logger.info(f"В БД найдено состояний: {len(migrated)}")
            
            # Проверяем поисковые термины
            terms = repo.get_last_search_terms(user_id)
            if terms:
                logger.info(f"Последние поисковые термины в БД: {terms}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}", exc_info=True)
        return False


def verify_migration(user_id: int):
    """Проверить результаты миграции."""
    try:
        from webapp.db import get_db
        from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
        
        db = next(get_db())
        try:
            repo = FileSearchStateRepository(db)
            
            # Получаем все состояния
            all_states = repo.get_user_states(user_id)
            last_terms = repo.get_last_search_terms(user_id)
            
            logger.info("\n=== Результаты миграции ===")
            logger.info(f"User ID: {user_id}")
            logger.info(f"Всего состояний файлов в БД: {len(all_states)}")
            logger.info(f"Последние поисковые термины: {last_terms or '(пусто)'}")
            
            # Группируем по статусам
            by_status = {}
            for state in all_states:
                if state.status not in by_status:
                    by_status[state.status] = []
                by_status[state.status].append(state.file_path)
            
            logger.info("\nРаспределение по статусам:")
            for status in sorted(by_status.keys()):
                files = by_status[status]
                logger.info(f"  {status}: {len(files)} файлов")
                for file_path in files[:3]:
                    logger.info(f"    - {file_path}")
                if len(files) > 3:
                    logger.info(f"    ... и ещё {len(files) - 3}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}", exc_info=True)
        return False


def main():
    """Главная функция скрипта."""
    parser = argparse.ArgumentParser(
        description='Миграция состояний файлов из search_results.json в PostgreSQL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только показать что будет сделано, без изменений в БД'
    )
    parser.add_argument(
        '--file',
        default='index/search_results.json',
        help='Путь к файлу search_results.json (по умолчанию: index/search_results.json)'
    )
    parser.add_argument(
        '--user-id',
        type=int,
        required=True,
        help='ID пользователя (обязательно для multi-user окружения)'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Только проверить результаты миграции без повторного импорта'
    )
    
    args = parser.parse_args()
    
    # Проверяем переменные окружения
    if not os.environ.get('DATABASE_URL'):
        logger.error("❌ Не установлена переменная окружения DATABASE_URL")
        logger.info("Укажите её в .env файле или экспортируйте:")
        logger.info("  export DATABASE_URL='postgresql://user:pass@localhost:5432/dbname'")
        return 1
    
    if args.verify:
        logger.info(f"Проверка результатов миграции для user_id={args.user_id}...")
        success = verify_migration(args.user_id)
        return 0 if success else 1
    
    # Загружаем данные из файла
    logger.info(f"Загрузка состояний из {args.file}...")
    states_data = load_states_from_file(args.file)
    
    if not states_data.get('file_status'):
        logger.warning("⚠️  Файл не содержит состояний файлов (возможно, он пустой)")
        logger.info("Это нормально, если поиск ещё не выполнялся")
        return 0
    
    # Выполняем миграцию
    logger.info("Начинаем миграцию...")
    success = migrate_states_to_db(states_data, args.user_id, dry_run=args.dry_run)
    
    if success and not args.dry_run:
        # Проверяем результат
        logger.info("\nПроверка результатов...")
        verify_migration(args.user_id)
        
        logger.info("\n✅ Миграция завершена успешно!")
        logger.info("\nСледующие шаги:")
        logger.info("1. Убедитесь, что USE_DATABASE=true в .env")
        logger.info("2. Перезапустите приложение")
        logger.info("3. Проверьте работу поиска")
        logger.info("4. После проверки можно удалить index/search_results.json")
        return 0
    elif success and args.dry_run:
        logger.info("\n✅ Dry-run проверка прошла успешно")
        logger.info("Запустите без --dry-run для реальной миграции")
        return 0
    else:
        logger.error("\n❌ Миграция завершена с ошибками")
        return 1


if __name__ == '__main__':
    sys.exit(main())
