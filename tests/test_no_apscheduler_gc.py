"""
Тесты отсутствия автоматического GC через APScheduler (инкремент 020, Блок 8).

Проверяем что планировщик больше не инициализируется автоматически.
"""

import pytest


def test_scheduler_not_imported_in_init():
    """
    Проверка: webapp/__init__.py НЕ импортирует start_scheduler.
    
    Новая архитектура (инкремент 020):
    - Prune происходит on-write при загрузке файлов
    - Периодический планировщик не используется
    """
    import webapp
    from pathlib import Path
    
    init_path = Path(webapp.__file__)
    init_content = init_path.read_text(encoding='utf-8')
    
    # Проверяем что start_scheduler НЕ импортируется
    assert 'from webapp.services.scheduler import start_scheduler' not in init_content, (
        "start_scheduler не должен импортироваться в webapp/__init__.py"
    )
    
    # Проверяем что start_scheduler НЕ вызывается
    assert 'start_scheduler(app)' not in init_content, (
        "start_scheduler(app) не должен вызываться в webapp/__init__.py"
    )
    
    # Проверяем что есть комментарий о новой архитектуре
    assert 'on-write enforcement' in init_content, (
        "Должен быть комментарий о новой архитектуре (on-write enforcement)"
    )


def test_blob_storage_service_has_prune():
    """
    Проверка: BlobStorageService содержит метод check_size_limit_and_prune().
    
    Это новый способ очистки БД - автоматически при загрузке файлов.
    """
    from webapp.services.blob_storage_service import BlobStorageService
    
    # Проверяем наличие метода
    assert hasattr(BlobStorageService, 'check_size_limit_and_prune'), (
        "BlobStorageService должен иметь метод check_size_limit_and_prune()"
    )
    
    # Проверяем что метод вызываемый
    assert callable(BlobStorageService.check_size_limit_and_prune), (
        "check_size_limit_and_prune() должен быть вызываемым методом"
    )


def test_scheduler_file_marked_deprecated():
    """
    Проверка: scheduler.py помечен как DEPRECATED.
    
    Файл оставлен для обратной совместимости, но не используется.
    """
    from pathlib import Path
    import webapp.services
    
    scheduler_path = Path(webapp.services.__file__).parent / 'scheduler.py'
    
    if scheduler_path.exists():
        scheduler_content = scheduler_path.read_text(encoding='utf-8')
        
        # Проверяем наличие метки DEPRECATED
        assert 'DEPRECATED' in scheduler_content, (
            "scheduler.py должен быть помечен как DEPRECATED"
        )
        
        assert 'ИНКРЕМЕНТ 020' in scheduler_content or 'Блок 8' in scheduler_content, (
            "scheduler.py должен содержать ссылку на инкремент 020 или Блок 8"
        )


def test_admin_routes_no_scheduler_imports():
    """
    Проверка: admin.py НЕ импортирует функции планировщика.
    
    Старые эндпоинты /admin/scheduler/* удалены.
    """
    from pathlib import Path
    import webapp.routes.admin
    
    admin_path = Path(webapp.routes.admin.__file__)
    admin_content = admin_path.read_text(encoding='utf-8')
    
    # Проверяем что scheduler НЕ импортируется
    assert 'from webapp.services.scheduler import schedule_gc_job' not in admin_content, (
        "schedule_gc_job не должен импортироваться в admin.py"
    )
    
    assert 'from webapp.services.scheduler import unschedule_gc_job' not in admin_content, (
        "unschedule_gc_job не должен импортироваться в admin.py"
    )
    
    # Проверяем что есть комментарий о новой архитектуре
    assert 'on-write enforcement' in admin_content or 'ИНКРЕМЕНТ 020' in admin_content, (
        "Должен быть комментарий о новой архитектуре или ссылка на инкремент 020"
    )

