"""
Обработчик логов для записи в PostgreSQL.
"""
import logging
import traceback
from datetime import datetime
from flask import has_request_context, request, g
from webapp.db.base import SessionLocal


class DatabaseLogHandler(logging.Handler):
    """Handler для записи логов в таблицу app_logs."""
    
    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self.session_factory = SessionLocal
    
    def emit(self, record):
        """Записать лог в БД."""
        try:
            # Отложенный импорт моделей для избежания циклических зависимостей
            from webapp.db.models import AppLog
            
            session = self.session_factory()
            
            # Определяем user_id если есть контекст запроса
            user_id = None
            if has_request_context() and hasattr(g, 'user') and g.user:
                user_id = g.user.id
            
            # Формируем контекст
            context_json = {}
            if record.exc_info:
                context_json['exception'] = {
                    'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                    'value': str(record.exc_info[1]) if record.exc_info[1] else None,
                }
            
            if hasattr(record, 'extra') and record.extra:
                context_json.update(record.extra)
            
            # Создаём запись лога
            log_entry = AppLog(
                level=record.levelname,
                user_id=user_id,
                component=record.name,
                message=record.getMessage(),
                context_json=context_json if context_json else None,
                created_at=datetime.utcnow()
            )
            
            session.add(log_entry)
            session.commit()
            session.close()
            
        except Exception:
            # Не падаем если не удалось записать лог в БД
            # Можно добавить fallback на файловое логирование
            pass


class HTTPRequestLogHandler:
    """Middleware для логирования HTTP запросов в БД."""
    
    @staticmethod
    def log_request(app, request, response, start_time):
        """Записать информацию о HTTP запросе."""
        try:
            import time
            # Отложенный импорт моделей для избежания циклических зависимостей
            from webapp.db.models import HTTPRequestLog
            
            session = SessionLocal()
            
            # Определяем user_id
            user_id = None
            if hasattr(g, 'user') and g.user:
                user_id = g.user.id
            
            # Вычисляем время обработки
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Получаем query parameters
            query_params = dict(request.args) if request.args else None
            
            # Получаем тело запроса (только для POST/PUT/PATCH, ограничиваем размер)
            request_body = None
            if request.method in ('POST', 'PUT', 'PATCH'):
                try:
                    if request.content_length and request.content_length < 10000:  # Макс 10KB
                        request_body = request.get_data(as_text=True)
                except Exception:
                    pass
            
            # Создаём запись
            log_entry = HTTPRequestLog(
                user_id=user_id,
                method=request.method,
                path=request.path,
                query_params=query_params,
                request_body=request_body,
                response_status=response.status_code,
                response_time_ms=response_time_ms,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                created_at=datetime.utcnow()
            )
            
            session.add(log_entry)
            session.commit()
            session.close()
            
        except Exception as e:
            # Логируем ошибку но не падаем
            app.logger.debug(f'Ошибка записи HTTP лога в БД: {e}')


class ErrorLogHandler:
    """Handler для логирования ошибок в БД."""
    
    @staticmethod
    def log_error(app, error, user_id=None, request_path=None, request_data=None, component=None):
        """Записать информацию об ошибке."""
        try:
            # Отложенный импорт моделей для избежания циклических зависимостей
            from webapp.db.models import ErrorLog
            
            session = SessionLocal()
            
            # Получаем информацию об ошибке
            error_type = type(error).__name__
            error_message = str(error)
            
            # Получаем traceback
            stack_trace = None
            if hasattr(error, '__traceback__'):
                stack_trace = ''.join(traceback.format_tb(error.__traceback__))
            
            # Определяем компонент
            if not component:
                component = 'unknown'
                if hasattr(error, '__module__'):
                    component = error.__module__
            
            # Получаем путь запроса
            if not request_path and has_request_context():
                request_path = request.path
            
            # Получаем данные запроса
            if not request_data and has_request_context():
                try:
                    request_data = {
                        'method': request.method,
                        'args': dict(request.args),
                        'form': dict(request.form) if request.form else None,
                    }
                except Exception:
                    pass
            
            # Определяем user_id
            if not user_id and has_request_context() and hasattr(g, 'user') and g.user:
                user_id = g.user.id
            
            # Создаём запись
            error_entry = ErrorLog(
                user_id=user_id,
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
                component=component,
                request_path=request_path,
                request_data=request_data,
                context_json=None,
                is_resolved=False,
                created_at=datetime.utcnow()
            )
            
            session.add(error_entry)
            session.commit()
            session.close()
            
        except Exception as e:
            # Логируем но не падаем
            app.logger.debug(f'Ошибка записи error log в БД: {e}')
