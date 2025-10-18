"""Глобальное хранилище прогресса индексации для real-time обновлений."""
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class IndexingProgress:
    """Текущее состояние индексации."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    current_file_progress: int = 0  # процент обработки текущего файла
    status: str = "idle"  # idle, running, completed, error
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def percent(self) -> int:
        """Общий процент завершения."""
        if self.total_files == 0:
            return 0
        return int((self.processed_files / self.total_files) * 100)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь для JSON."""
        data = asdict(self)
        data['percent'] = self.percent
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data


class IndexingProgressManager:
    """Потокобезопасный менеджер прогресса индексации."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._progress = IndexingProgress()
    
    def start(self, total_files: int):
        """Начать новую индексацию."""
        with self._lock:
            self._progress = IndexingProgress(
                total_files=total_files,
                processed_files=0,
                current_file="",
                status="running",
                start_time=datetime.now()
            )
    
    def update(self, processed: int, current_file: str, file_progress: int = 0):
        """Обновить прогресс."""
        with self._lock:
            self._progress.processed_files = processed
            self._progress.current_file = current_file
            self._progress.current_file_progress = file_progress
    
    def complete(self):
        """Завершить индексацию успешно."""
        with self._lock:
            self._progress.status = "completed"
            self._progress.end_time = datetime.now()
            self._progress.current_file = ""
    
    def error(self, error_message: str):
        """Завершить индексацию с ошибкой."""
        with self._lock:
            self._progress.status = "error"
            self._progress.error = error_message
            self._progress.end_time = datetime.now()
    
    def get_progress(self) -> IndexingProgress:
        """Получить текущий снимок прогресса."""
        with self._lock:
            # Возвращаем копию
            return IndexingProgress(
                total_files=self._progress.total_files,
                processed_files=self._progress.processed_files,
                current_file=self._progress.current_file,
                current_file_progress=self._progress.current_file_progress,
                status=self._progress.status,
                error=self._progress.error,
                start_time=self._progress.start_time,
                end_time=self._progress.end_time
            )
    
    def reset(self):
        """Сбросить прогресс."""
        with self._lock:
            self._progress = IndexingProgress()


# Глобальный экземпляр менеджера прогресса
_global_progress_manager = IndexingProgressManager()


def get_progress_manager() -> IndexingProgressManager:
    """Получить глобальный менеджер прогресса."""
    return _global_progress_manager
