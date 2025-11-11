"""
[DEPRECATED - ИНКРЕМЕНТ 020, Блок 8]

Планировщик автоматического запуска Garbage Collection.

⚠️ УСТАРЕЛ: APScheduler для периодического GC больше не используется.

Новая архитектура (инкремент 020):
- Prune происходит автоматически при загрузке файлов (on-write enforcement)
- Проверка лимита и удаление 30% в BlobStorageService.check_size_limit_and_prune()
- Настройки: AUTO_PRUNE_ENABLED и DB_SIZE_LIMIT_BYTES в таблице app_settings
- Админ-панель: /admin/settings для управления прунингом

Этот файл оставлен для обратной совместимости, но функции не вызываются.
Может быть полностью удалён в следующем инкременте.
"""

from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, current_app


# Глобальный планировщик
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    """
    Получить экземпляр планировщика.
    
    Returns:
        BackgroundScheduler или None если не инициализирован
    """
    return _scheduler


def init_scheduler(app: Flask) -> BackgroundScheduler:
    """
    Инициализирует планировщик с привязкой к Flask приложению.
    
    Args:
        app: Flask приложение
        
    Returns:
        Инстанс BackgroundScheduler
    """
    global _scheduler
    
    if _scheduler is not None:
        app.logger.warning('Планировщик уже инициализирован')
        return _scheduler
    
    # Создаём планировщик
    _scheduler = BackgroundScheduler(
        timezone='Europe/Moscow',  # MSK
        daemon=True,
        job_defaults={
            'coalesce': True,  # Объединять пропущенные запуски
            'max_instances': 1  # Не более 1 экземпляра задачи одновременно
        }
    )
    
    app.logger.info('Планировщик инициализирован (timezone=Europe/Moscow)')
    
    return _scheduler


def start_scheduler(app: Flask):
    """
    Запускает планировщик и добавляет задачу GC если включено в конфиге.
    
    Args:
        app: Flask приложение
    """
    global _scheduler
    
    if _scheduler is None:
        _scheduler = init_scheduler(app)
    
    if _scheduler.running:
        app.logger.warning('Планировщик уже запущен')
        return
    
    # Запускаем планировщик
    _scheduler.start()
    app.logger.info('Планировщик запущен')
    
    # Проверяем конфигурацию и добавляем задачу GC если включено
    from webapp.config.config_service import get_config
    config = get_config()
    
    gc_enabled = config.get('GC_SCHEDULE_ENABLED', False)
    if gc_enabled:
        schedule_gc_job(app)
    else:
        app.logger.info('Автоматический GC отключён в конфигурации')


def stop_scheduler(app: Flask):
    """
    Останавливает планировщик.
    
    Args:
        app: Flask приложение
    """
    global _scheduler
    
    if _scheduler is None or not _scheduler.running:
        app.logger.warning('Планировщик не запущен')
        return
    
    _scheduler.shutdown(wait=False)
    app.logger.info('Планировщик остановлен')


def schedule_gc_job(app: Flask, remove_existing: bool = True):
    """
    Добавляет задачу автоматического GC в планировщик.
    
    Args:
        app: Flask приложение
        remove_existing: Удалить существующую задачу GC перед добавлением
    """
    global _scheduler
    
    if _scheduler is None:
        app.logger.error('Планировщик не инициализирован')
        return
    
    from webapp.config.config_service import get_config
    config = get_config()
    
    # Параметры из конфига
    gc_hour = config.get('GC_SCHEDULE_HOUR', 3)  # По умолчанию 3:00
    gc_threshold = config.get('GC_THRESHOLD_SCORE', -10.0)
    gc_max_deletions = config.get('GC_MAX_DELETIONS', 100)
    
    # Удаляем существующую задачу если есть
    if remove_existing:
        try:
            _scheduler.remove_job('auto_gc')
            app.logger.info('Существующая задача auto_gc удалена')
        except Exception:
            pass  # Задачи не было
    
    # Добавляем новую задачу
    trigger = CronTrigger(hour=gc_hour, minute=0, timezone='Europe/Moscow')
    
    _scheduler.add_job(
        func=_run_gc_task,
        trigger=trigger,
        id='auto_gc',
        name='Автоматический Garbage Collection',
        kwargs={
            'threshold_score': gc_threshold,
            'max_deletions': gc_max_deletions
        },
        replace_existing=True
    )
    
    app.logger.info(
        f'Задача auto_gc запланирована: каждый день в {gc_hour}:00 MSK '
        f'(threshold={gc_threshold}, max_deletions={gc_max_deletions})'
    )


def unschedule_gc_job(app: Flask):
    """
    Удаляет задачу GC из планировщика.
    
    Args:
        app: Flask приложение
    """
    global _scheduler
    
    if _scheduler is None:
        app.logger.error('Планировщик не инициализирован')
        return
    
    try:
        _scheduler.remove_job('auto_gc')
        app.logger.info('Задача auto_gc удалена из планировщика')
    except Exception as e:
        app.logger.warning(f'Не удалось удалить задачу auto_gc: {e}')


def _run_gc_task(threshold_score: float = -10.0, max_deletions: int = 100):
    """
    Внутренняя функция для запуска GC.
    
    Выполняется в контексте планировщика.
    
    Args:
        threshold_score: Порог retention score
        max_deletions: Максимальное количество удалений
    """
    from webapp.models.rag_models import RAGDatabase
    from webapp.services.gc_service import run_garbage_collection
    
    try:
        current_app.logger.info(
            f'Автоматический GC запущен (threshold={threshold_score}, max_deletions={max_deletions})'
        )
        
        # Подключаемся к БД
        db = RAGDatabase()
        
        # Запускаем GC (не dry-run)
        result = run_garbage_collection(
            db=db,
            threshold_score=threshold_score,
            max_deletions=max_deletions,
            dry_run=False,
            audit_log_path='logs/storage_audit.log'
        )
        
        # Логируем результат
        current_app.logger.info(
            f'Автоматический GC завершён: '
            f'кандидатов={result.get("candidates_found", 0)}, '
            f'удалено документов={result.get("documents_deleted", 0)}, '
            f'удалено чанков={result.get("chunks_deleted", 0)}'
        )
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка автоматического GC: {e}')


def get_scheduler_status() -> dict:
    """
    Получить текущий статус планировщика.
    
    Returns:
        Словарь с полями:
        - running: bool - планировщик запущен
        - gc_job_scheduled: bool - задача GC добавлена
        - next_run_time: str | None - время следующего запуска GC
        - jobs_count: int - количество задач
    """
    global _scheduler
    
    if _scheduler is None:
        return {
            'running': False,
            'gc_job_scheduled': False,
            'next_run_time': None,
            'jobs_count': 0
        }
    
    status = {
        'running': _scheduler.running,
        'gc_job_scheduled': False,
        'next_run_time': None,
        'jobs_count': len(_scheduler.get_jobs())
    }
    
    # Ищем задачу GC
    try:
        gc_job = _scheduler.get_job('auto_gc')
        if gc_job:
            status['gc_job_scheduled'] = True
            if gc_job.next_run_time:
                status['next_run_time'] = gc_job.next_run_time.isoformat()
    except Exception:
        pass
    
    return status
