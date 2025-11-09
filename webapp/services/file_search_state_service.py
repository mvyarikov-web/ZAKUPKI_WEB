"""
Сервис для работы с состояниями файлов при поиске.
Замена legacy FilesState с автоматическим переключением между БД и файлом.
"""
import os
import json
import fcntl
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from flask import current_app, g

logger = logging.getLogger(__name__)


class FileSearchStateService:
    """Сервис для работы с состояниями файлов при поиске."""
    
    def __init__(self, state_file: Optional[str] = None):
        """
        Инициализация сервиса.
        
        Args:
            state_file: Путь к legacy файлу состояния (для обратной совместимости)
        """
        self.use_database = self._should_use_database()
        self.state_file = state_file or self._get_default_state_file()
        
        if not self.use_database:
            self._ensure_file_exists()
    
    def _should_use_database(self) -> bool:
        """Определить, использовать ли БД."""
        try:
            if current_app:
                return current_app.config.get('use_database', False)
        except Exception:
            pass
        return os.environ.get('USE_DATABASE', 'false').lower() in ('true', '1', 'yes', 'on')
    
    def _get_default_state_file(self) -> str:
        """Получить путь к default файлу состояния."""
        try:
            if current_app:
                return current_app.config.get('SEARCH_RESULTS_FILE', 'index/search_results.json')
        except Exception:
            pass
        return 'index/search_results.json'
    
    def _get_user_id(self) -> Optional[int]:
        """Получить ID текущего пользователя из контекста Flask."""
        try:
            if hasattr(g, 'user') and g.user:
                return g.user.id
        except Exception:
            pass
        return None
    
    def _ensure_file_exists(self):
        """Создаёт файл состояния, если он не существует."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        if not os.path.exists(self.state_file):
            self._write_state_file({
                'last_updated': datetime.now().isoformat(),
                'file_status': {},
                'last_search_terms': ''
            })
    
    def _read_state_file(self) -> Dict[str, Any]:
        """Читает состояние из файла с блокировкой."""
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock для чтения
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f'Ошибка чтения состояния из файла: {e}')
            return {
                'last_updated': datetime.now().isoformat(),
                'file_status': {},
                'last_search_terms': ''
            }
    
    def _write_state_file(self, data: Dict[str, Any]):
        """Записывает состояние в файл с блокировкой."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock для записи
                try:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.exception(f'Ошибка записи состояния в файл: {e}')
    
    def _read_state_db(self, user_id: int) -> Dict[str, Any]:
        """Читает состояние из БД."""
        from webapp.db import get_db
        from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
        
        db = next(get_db())
        try:
            repo = FileSearchStateRepository(db)
            return repo.to_legacy_format(user_id)
        finally:
            db.close()
    
    def get_file_status(self, filepath: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает статус файла или всех файлов.
        
        Args:
            filepath: Путь к файлу (если None, вернет все статусы)
            
        Returns:
            Словарь со статусом файла или всех файлов
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                return {}
            
            data = self._read_state_db(user_id)
        else:
            data = self._read_state_file()
        
        file_status = data.get('file_status', {})
        if filepath:
            return file_status.get(filepath, {'status': 'not_checked'})
        return file_status
    
    def set_file_status(self, filepath: str, status: str, result: Optional[Dict] = None):
        """
        Устанавливает статус файла.
        
        Args:
            filepath: Путь к файлу
            status: Статус файла (not_checked, processing, contains_keywords, no_keywords, error)
            result: Дополнительная информация о результате
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                logger.warning("Невозможно сохранить статус файла: пользователь не авторизован")
                return
            
            from webapp.db import get_db
            from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
            
            db = next(get_db())
            try:
                repo = FileSearchStateRepository(db)
                repo.set_file_status(
                    user_id=user_id,
                    file_path=filepath,
                    status=status,
                    result=result
                )
            finally:
                db.close()
        else:
            data = self._read_state_file()
            file_status = data.get('file_status', {})
            
            file_status[filepath] = {
                'status': status,
                'result': result or {}
            }
            
            data['file_status'] = file_status
            data['last_updated'] = datetime.now().isoformat()
            
            self._write_state_file(data)
    
    def update_file_statuses(self, statuses: Dict[str, Dict[str, Any]]):
        """
        Обновляет статусы нескольких файлов атомарно.
        
        Args:
            statuses: Словарь {filepath: {'status': ..., 'result': ...}}
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                logger.warning("Невозможно обновить статусы файлов: пользователь не авторизован")
                return
            
            from webapp.db import get_db
            from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
            
            db = next(get_db())
            try:
                repo = FileSearchStateRepository(db)
                repo.update_file_statuses(user_id, statuses)
            finally:
                db.close()
        else:
            data = self._read_state_file()
            file_status = data.get('file_status', {})
            
            file_status.update(statuses)
            
            data['file_status'] = file_status
            data['last_updated'] = datetime.now().isoformat()
            
            self._write_state_file(data)
    
    def clear(self):
        """Очищает все статусы."""
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                return
            
            from webapp.db import get_db
            from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
            
            db = next(get_db())
            try:
                repo = FileSearchStateRepository(db)
                repo.clear_user_states(user_id)
            finally:
                db.close()
        else:
            self._write_state_file({
                'last_updated': datetime.now().isoformat(),
                'file_status': {},
                'last_search_terms': ''
            })
    
    def get_last_search_terms(self) -> str:
        """
        Получает последние поисковые термины.
        
        Returns:
            Строка с терминами
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                return ''
            
            from webapp.db import get_db
            from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
            
            db = next(get_db())
            try:
                repo = FileSearchStateRepository(db)
                return repo.get_last_search_terms(user_id)
            finally:
                db.close()
        else:
            data = self._read_state_file()
            return data.get('last_search_terms', '')
    
    def set_last_search_terms(self, terms: str):
        """
        Сохраняет последние поисковые термины.
        
        Args:
            terms: Строка с терминами
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                return
            
            from webapp.db import get_db
            from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository
            
            db = next(get_db())
            try:
                repo = FileSearchStateRepository(db)
                repo.set_last_search_terms(user_id, terms)
            finally:
                db.close()
        else:
            data = self._read_state_file()
            data['last_search_terms'] = terms
            data['last_updated'] = datetime.now().isoformat()
            self._write_state_file(data)
    
    def get_all(self) -> Dict[str, Any]:
        """
        Получает все состояние.
        
        Returns:
            Полный словарь состояния
        """
        if self.use_database:
            user_id = self._get_user_id()
            if not user_id:
                return {
                    'last_updated': datetime.now().isoformat(),
                    'file_status': {},
                    'last_search_terms': ''
                }
            
            return self._read_state_db(user_id)
        else:
            return self._read_state_file()
