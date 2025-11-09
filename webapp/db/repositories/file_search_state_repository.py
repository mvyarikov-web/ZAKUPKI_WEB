"""
Репозиторий для работы с состояниями файлов при поиске.
Замена legacy файла search_results.json.
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from webapp.db.models import FileSearchState
from webapp.db.repositories.base_repository import BaseRepository


class FileSearchStateRepository(BaseRepository[FileSearchState]):
    """Репозиторий для работы с состояниями файлов при поиске."""
    
    def __init__(self, session: Session):
        super().__init__(session, FileSearchState)
    
    def get_by_user_and_file(self, user_id: int, file_path: str) -> Optional[FileSearchState]:
        """Получить состояние файла для пользователя."""
        return self.session.query(FileSearchState).filter(
            and_(
                FileSearchState.user_id == user_id,
                FileSearchState.file_path == file_path
            )
        ).first()
    
    def get_user_states(self, user_id: int, status: Optional[str] = None) -> List[FileSearchState]:
        """Получить все состояния файлов пользователя."""
        query = self.session.query(FileSearchState).filter(
            FileSearchState.user_id == user_id
        )
        if status:
            query = query.filter(FileSearchState.status == status)
        return query.order_by(FileSearchState.updated_at.desc()).all()
    
    def set_file_status(
        self, 
        user_id: int, 
        file_path: str, 
        status: str,
        result: Optional[Dict] = None,
        search_terms: Optional[str] = None
    ) -> FileSearchState:
        """Установить или обновить статус файла."""
        existing = self.get_by_user_and_file(user_id, file_path)
        
        if existing:
            # Обновляем существующее состояние
            existing.status = status
            if result is not None:
                existing.result_json = result
            if search_terms is not None:
                existing.search_terms = search_terms
            existing.last_checked_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            return existing
        else:
            # Создаём новое состояние
            state = FileSearchState(
                user_id=user_id,
                file_path=file_path,
                status=status,
                result_json=result or {},
                search_terms=search_terms or '',
                last_checked_at=datetime.utcnow()
            )
            self.session.add(state)
            self.session.commit()
            return state
    
    def update_file_statuses(self, user_id: int, statuses: Dict[str, Dict[str, Any]]) -> None:
        """
        Обновить статусы нескольких файлов атомарно.
        
        Args:
            user_id: ID пользователя
            statuses: Словарь {file_path: {'status': ..., 'result': ...}}
        """
        for file_path, data in statuses.items():
            self.set_file_status(
                user_id=user_id,
                file_path=file_path,
                status=data.get('status', 'not_checked'),
                result=data.get('result'),
                search_terms=data.get('search_terms')
            )
    
    def clear_user_states(self, user_id: int) -> int:
        """Очистить все состояния файлов пользователя."""
        count = self.session.query(FileSearchState).filter(
            FileSearchState.user_id == user_id
        ).delete()
        self.session.commit()
        return count
    
    def get_last_search_terms(self, user_id: int) -> str:
        """Получить последние поисковые термины пользователя."""
        state = self.session.query(FileSearchState).filter(
            FileSearchState.user_id == user_id
        ).order_by(FileSearchState.updated_at.desc()).first()
        
        return state.search_terms if state and state.search_terms else ''
    
    def set_last_search_terms(self, user_id: int, terms: str) -> None:
        """
        Сохранить последние поисковые термины.
        Обновляет search_terms для всех файлов пользователя.
        """
        self.session.query(FileSearchState).filter(
            FileSearchState.user_id == user_id
        ).update({FileSearchState.search_terms: terms})
        self.session.commit()
    
    def to_legacy_format(self, user_id: int) -> Dict[str, Any]:
        """
        Конвертировать состояния в формат legacy search_results.json.
        Для обратной совместимости со старым кодом.
        """
        states = self.get_user_states(user_id)
        
        file_status = {}
        last_search_terms = ''
        last_updated = None
        
        for state in states:
            file_status[state.file_path] = {
                'status': state.status,
                'result': state.result_json or {}
            }
            if state.search_terms and not last_search_terms:
                last_search_terms = state.search_terms
            if not last_updated or state.updated_at > last_updated:
                last_updated = state.updated_at
        
        return {
            'last_updated': last_updated.isoformat() if last_updated else datetime.utcnow().isoformat(),
            'file_status': file_status,
            'last_search_terms': last_search_terms
        }
    
    def from_legacy_format(self, user_id: int, legacy_data: Dict[str, Any]) -> None:
        """
        Импортировать данные из legacy формата search_results.json в БД.
        Используется для миграции.
        """
        file_status = legacy_data.get('file_status', {})
        search_terms = legacy_data.get('last_search_terms', '')
        
        for file_path, data in file_status.items():
            self.set_file_status(
                user_id=user_id,
                file_path=file_path,
                status=data.get('status', 'not_checked'),
                result=data.get('result'),
                search_terms=search_terms
            )
