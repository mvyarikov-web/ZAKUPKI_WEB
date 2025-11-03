"""
Базовый репозиторий с общими CRUD операциями.
"""
from typing import TypeVar, Generic, Type, Optional, List, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete, func
from webapp.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Базовый класс для всех репозиториев с общими CRUD операциями.
    
    Attributes:
        model: SQLAlchemy модель для работы
        session: Сессия БД
    """
    
    def __init__(self, model: Type[ModelType], session: Session):
        """
        Args:
            model: SQLAlchemy модель
            session: Активная сессия БД
        """
        self.model = model
        self.session = session
    
    def create(self, **kwargs) -> ModelType:
        """
        Создать новую запись.
        
        Args:
            **kwargs: Поля модели
            
        Returns:
            Созданный объект
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance
    
    def get_by_id(self, id: int) -> Optional[ModelType]:
        """
        Получить запись по ID.
        
        Args:
            id: ID записи
            
        Returns:
            Объект или None
        """
        stmt = select(self.model).where(self.model.id == id)
        return self.session.execute(stmt).scalar_one_or_none()
    
    def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[ModelType]:
        """
        Получить все записи с пагинацией.
        
        Args:
            limit: Макс. кол-во записей (None = все)
            offset: Смещение
            
        Returns:
            Список объектов
        """
        stmt = select(self.model).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())
    
    def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """
        Обновить запись по ID.
        
        Args:
            id: ID записи
            **kwargs: Поля для обновления
            
        Returns:
            Обновлённый объект или None
        """
        instance = self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            self.session.commit()
            self.session.refresh(instance)
        return instance
    
    def delete(self, id: int) -> bool:
        """
        Удалить запись по ID.
        
        Args:
            id: ID записи
            
        Returns:
            True если удалено, False если не найдено
        """
        instance = self.get_by_id(id)
        if instance:
            self.session.delete(instance)
            self.session.commit()
            return True
        return False
    
    def count(self, **filters) -> int:
        """
        Подсчитать количество записей с фильтрами.
        
        Args:
            **filters: Условия фильтрации
            
        Returns:
            Количество записей
        """
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        return self.session.execute(stmt).scalar_one()
    
    def exists(self, **filters) -> bool:
        """
        Проверить существование записи с фильтрами.
        
        Args:
            **filters: Условия фильтрации
            
        Returns:
            True если запись существует
        """
        return self.count(**filters) > 0
    
    def find_one(self, **filters) -> Optional[ModelType]:
        """
        Найти одну запись по фильтрам.
        
        Args:
            **filters: Условия фильтрации
            
        Returns:
            Объект или None
        """
        stmt = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        return self.session.execute(stmt).scalar_one_or_none()
    
    def find_all(self, limit: Optional[int] = None, offset: int = 0, **filters) -> List[ModelType]:
        """
        Найти все записи по фильтрам с пагинацией.
        
        Args:
            limit: Макс. кол-во записей
            offset: Смещение
            **filters: Условия фильтрации
            
        Returns:
            Список объектов
        """
        stmt = select(self.model).offset(offset)
        for key, value in filters.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())
