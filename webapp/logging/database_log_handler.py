"""
Кастомный logging handler для записи логов в БД.
"""
import logging
import re
from typing import Optional

from webapp.db.repositories import AppLogRepository


class DatabaseLogHandler(logging.Handler):
    """
    Handler для записи логов в таблицу app_logs.
    
    Поддерживает:
    - Маскирование секретов (пароли, API-ключи)
    - Запись контекста в context_json
    - Привязку к пользователю через user_id
    """
    
    # Паттерны для маскирования секретов (порядок важен - более специфичные первыми!)
    SECRET_PATTERNS = [
        # API ключи (специфичные префиксы первыми, минимум 10 символов)
        (r'(sk-proj-[a-zA-Z0-9_-]{10,})', r'sk-proj-****'),
        (r'(sk-ant-[a-zA-Z0-9_-]{10,})', r'sk-ant-****'),
        (r'(pplx-[a-zA-Z0-9_-]{10,})', r'pplx-****'),
        (r'(sk-[a-zA-Z0-9_-]{10,})', r'sk-****'),  # Общий sk- в конце
        
        # Пароли
        (r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', r'\1****'),
        (r'(pwd["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', r'\1****'),
        
        # Токены
        (r'(token["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', r'\1****'),
        (r'(bearer\s+)([a-zA-Z0-9_\-\.]+)', r'\1****', re.IGNORECASE),
        
        # Email (частичное)
        (r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'***@\2'),
    ]
    
    def __init__(
        self,
        session_factory,
        level=logging.INFO,
        component: Optional[str] = None
    ):
        """
        Args:
            session_factory: Callable для создания DB сессии
            level: Минимальный уровень логирования
            component: Имя компонента (по умолчанию берётся из record)
        """
        super().__init__(level)
        self.session_factory = session_factory
        self.component = component
    
    @staticmethod
    def mask_secrets(message: str) -> str:
        """
        Маскировать секреты в сообщении.
        
        Args:
            message: Исходное сообщение
            
        Returns:
            Сообщение с замаскированными секретами
        """
        masked = message
        
        for pattern, replacement, *flags in DatabaseLogHandler.SECRET_PATTERNS:
            flags_value = flags[0] if flags else 0
            masked = re.sub(pattern, replacement, masked, flags=flags_value)
        
        return masked
    
    def emit(self, record: logging.LogRecord):
        """
        Записать лог-запись в БД.
        
        Args:
            record: LogRecord от logging
        """
        try:
            # Создаём сессию
            session = self.session_factory()
            repo = AppLogRepository(session)
            
            # Форматируем сообщение
            message = self.format(record)
            
            # Маскируем секреты
            message = self.mask_secrets(message)
            
            # Извлекаем контекст
            context_json = None
            if hasattr(record, 'extra_json'):
                context_json = record.extra_json
            
            # Извлекаем user_id
            user_id = None
            if hasattr(record, 'user_id'):
                user_id = record.user_id
            
            # Определяем компонент
            component = self.component or record.name
            
            # Записываем в БД
            repo.create_log(
                level=record.levelname,
                message=message,
                component=component,
                user_id=user_id,
                context_json=context_json
            )
            
            session.close()
            
        except Exception:
            # Не падаем при ошибках логирования
            self.handleError(record)
    
    def close(self):
        """Закрыть handler."""
        super().close()
