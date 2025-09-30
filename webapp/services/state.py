"""Сервис для управления состоянием файлов с файловой блокировкой."""
import os
import json
import fcntl
from datetime import datetime
from typing import Dict, Any, Optional
from flask import current_app


class FilesState:
    """Управление состоянием файлов с атомарными операциями через файловую блокировку."""
    
    def __init__(self, state_file: str):
        """Инициализация.
        
        Args:
            state_file: Путь к файлу состояния (search_results.json)
        """
        self.state_file = state_file
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Создает файл состояния, если он не существует."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        if not os.path.exists(self.state_file):
            self._write_state({
                'last_updated': datetime.now().isoformat(),
                'file_status': {},
                'last_search_terms': ''
            })
    
    def _read_state(self) -> Dict[str, Any]:
        """Читает состояние из файла с блокировкой.
        
        Returns:
            Словарь с состоянием
        """
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock для чтения
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            current_app.logger.warning(f'Ошибка чтения состояния: {e}')
            return {
                'last_updated': datetime.now().isoformat(),
                'file_status': {},
                'last_search_terms': ''
            }
    
    def _write_state(self, data: Dict[str, Any]):
        """Записывает состояние в файл с блокировкой.
        
        Args:
            data: Данные для записи
        """
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock для записи
                try:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            current_app.logger.exception(f'Ошибка записи состояния: {e}')
    
    def get_file_status(self, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Получает статус файла или всех файлов.
        
        Args:
            filepath: Путь к файлу (если None, вернет все статусы)
            
        Returns:
            Словарь со статусом файла или всех файлов
        """
        data = self._read_state()
        file_status = data.get('file_status', {})
        if filepath:
            return file_status.get(filepath, {'status': 'not_checked'})
        return file_status
    
    def set_file_status(self, filepath: str, status: str, result: Optional[Dict] = None):
        """Устанавливает статус файла.
        
        Args:
            filepath: Путь к файлу
            status: Статус файла (not_checked, processing, contains_keywords, no_keywords, error)
            result: Дополнительная информация о результате
        """
        data = self._read_state()
        file_status = data.get('file_status', {})
        
        file_status[filepath] = {
            'status': status,
            'result': result or {}
        }
        
        data['file_status'] = file_status
        data['last_updated'] = datetime.now().isoformat()
        
        self._write_state(data)
    
    def update_file_statuses(self, statuses: Dict[str, Dict[str, Any]]):
        """Обновляет статусы нескольких файлов атомарно.
        
        Args:
            statuses: Словарь {filepath: {'status': ..., 'result': ...}}
        """
        data = self._read_state()
        file_status = data.get('file_status', {})
        
        file_status.update(statuses)
        
        data['file_status'] = file_status
        data['last_updated'] = datetime.now().isoformat()
        
        self._write_state(data)
    
    def clear(self):
        """Очищает все статусы."""
        self._write_state({
            'last_updated': datetime.now().isoformat(),
            'file_status': {},
            'last_search_terms': ''
        })
    
    def get_last_search_terms(self) -> str:
        """Получает последние поисковые термины.
        
        Returns:
            Строка с терминами
        """
        data = self._read_state()
        return data.get('last_search_terms', '')
    
    def set_last_search_terms(self, terms: str):
        """Сохраняет последние поисковые термины.
        
        Args:
            terms: Строка с терминами
        """
        data = self._read_state()
        data['last_search_terms'] = terms
        data['last_updated'] = datetime.now().isoformat()
        self._write_state(data)
    
    def get_all(self) -> Dict[str, Any]:
        """Получает все состояние.
        
        Returns:
            Полный словарь состояния
        """
        return self._read_state()
