#!/usr/bin/env python3
"""
Скрипт миграции конфигурации AI моделей из models.json в БД.

Использование:
    python scripts/migrate_models_to_db.py [--dry-run]
    
Опции:
    --dry-run    Только показать, что будет мигрировано, без изменений в БД
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


def load_models_from_file(file_path: str) -> dict:
    """Загрузить модели из JSON файла."""
    if not os.path.exists(file_path):
        logger.warning(f"Файл {file_path} не найден")
        return {'models': [], 'default_model': None}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Миграция старого формата (если это массив)
    if isinstance(data, list):
        data = {
            'models': data,
            'default_model': data[0]['model_id'] if data else None
        }
    
    # Нормализация ключей цен
    for model in data.get('models', []):
        if 'price_input_per_1M' in model:
            model['price_input_per_1m'] = model.pop('price_input_per_1M')
        if 'price_output_per_1M' in model:
            model['price_output_per_1m'] = model.pop('price_output_per_1M')
    
    return data


def migrate_models_to_db(models_data: dict, dry_run: bool = False) -> bool:
    """
    Мигрировать модели в БД.
    
    Args:
        models_data: Данные из models.json
        dry_run: Если True, только показать что будет сделано
    
    Returns:
        True если успешно, False при ошибке
    """
    from webapp.db import get_db
    from webapp.db.repositories.ai_model_config_repository import AIModelConfigRepository
    
    models = models_data.get('models', [])
    default_model_id = models_data.get('default_model')
    
    if not models:
        logger.warning("Нет моделей для миграции")
        return False
    
    logger.info(f"Найдено моделей для миграции: {len(models)}")
    logger.info(f"Модель по умолчанию: {default_model_id}")
    
    if dry_run:
        logger.info("\n=== DRY RUN MODE: Модели, которые будут мигрированы ===")
        for model in models:
            model_id = model.get('model_id', 'unknown')
            display_name = model.get('display_name', model_id)
            provider = model.get('provider', 'openai')
            enabled = model.get('enabled', True)
            is_default = model_id == default_model_id
            
            logger.info(f"  - {model_id} ({display_name})")
            logger.info(f"    Провайдер: {provider}")
            logger.info(f"    Включена: {enabled}")
            logger.info(f"    По умолчанию: {is_default}")
        
        logger.info("\n=== Миграция не выполнена (dry-run режим) ===")
        return True
    
    # Реальная миграция
    try:
        db = next(get_db())
        try:
            repo = AIModelConfigRepository(db)
            
            # Создаём таблицу если её нет
            try:
                from webapp.db.models import AIModelConfig
                bind = db.get_bind()
                AIModelConfig.__table__.create(bind=bind, checkfirst=True)
                logger.info("Таблица ai_model_configs проверена/создана")
            except Exception as e:
                logger.warning(f"Не удалось создать таблицу: {e}")
            
            # Импортируем модели
            logger.info("Начинаем импорт моделей...")
            repo.from_legacy_format(models_data)
            
            logger.info(f"✅ Успешно мигрировано {len(models)} моделей")
            
            # Проверяем результат
            migrated = repo.get_enabled_models()
            logger.info(f"В БД найдено моделей: {len(migrated)}")
            
            # Проверяем default модель
            default = repo.get_default_model()
            if default:
                logger.info(f"Модель по умолчанию в БД: {default.model_id}")
            else:
                logger.warning("Модель по умолчанию не установлена в БД")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}", exc_info=True)
        return False


def verify_migration():
    """Проверить результаты миграции."""
    try:
        from webapp.db import get_db
        from webapp.db.repositories.ai_model_config_repository import AIModelConfigRepository
        
        db = next(get_db())
        try:
            repo = AIModelConfigRepository(db)
            
            # Получаем все модели
            all_models = db.query(repo.model_class).all()
            enabled_models = repo.get_enabled_models()
            default_model = repo.get_default_model()
            
            logger.info("\n=== Результаты миграции ===")
            logger.info(f"Всего моделей в БД: {len(all_models)}")
            logger.info(f"Включённых моделей: {len(enabled_models)}")
            logger.info(f"Модель по умолчанию: {default_model.model_id if default_model else 'НЕ УСТАНОВЛЕНА'}")
            
            logger.info("\nСписок моделей:")
            for model in all_models:
                status = "✓" if model.is_enabled else "✗"
                default_mark = " [DEFAULT]" if model.is_default else ""
                logger.info(f"  {status} {model.model_id} ({model.display_name}){default_mark}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}", exc_info=True)
        return False


def main():
    """Главная функция скрипта."""
    parser = argparse.ArgumentParser(
        description='Миграция конфигурации AI моделей из models.json в PostgreSQL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только показать что будет сделано, без изменений в БД'
    )
    parser.add_argument(
        '--file',
        default='index/models.json',
        help='Путь к файлу models.json (по умолчанию: index/models.json)'
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
        logger.info("Проверка результатов миграции...")
        success = verify_migration()
        return 0 if success else 1
    
    # Загружаем данные из файла
    logger.info(f"Загрузка моделей из {args.file}...")
    models_data = load_models_from_file(args.file)
    
    if not models_data.get('models'):
        logger.error("❌ Не удалось загрузить модели из файла")
        return 1
    
    # Выполняем миграцию
    logger.info("Начинаем миграцию...")
    success = migrate_models_to_db(models_data, dry_run=args.dry_run)
    
    if success and not args.dry_run:
        # Проверяем результат
        logger.info("\nПроверка результатов...")
        verify_migration()
        
        logger.info("\n✅ Миграция завершена успешно!")
        logger.info("\nСледующие шаги:")
        logger.info("1. Убедитесь, что USE_DATABASE=true в .env")
        logger.info("2. Перезапустите приложение")
        logger.info("3. Проверьте работу AI-анализа")
        logger.info("4. После проверки можно удалить index/models.json")
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
