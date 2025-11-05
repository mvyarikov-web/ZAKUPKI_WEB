"""
Адаптер для dual-mode доступа к данным.

Переключение между файловым хранилищем (legacy) и базой данных PostgreSQL
в зависимости от флага use_database в конфигурации.

Цель: обеспечить плавный переход от файловой структуры к БД без ломания существующего UI.
"""
import os
import shutil
import logging
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from document_processor import DocumentProcessor
from document_processor.search.searcher import Searcher
from webapp.db.repositories.document_repository import DocumentRepository
from webapp.db.repositories.chunk_repository import ChunkRepository
from webapp.services.indexing import parse_index_char_counts

# Модульный логгер (не зависит от Flask context)
logger = logging.getLogger(__name__)


class DataAccessAdapter:
    """
    Адаптер для унифицированного доступа к данным в двух режимах:
    - use_database=False: legacy файловый режим (uploads/, index/_search_index.txt)
    - use_database=True: PostgreSQL режим (documents, chunks, pgvector)
    
    В режиме БД дополнительно синхронизирует _search_index.txt для legacy UI,
    если это требуется для обратной совместимости.
    """
    
    def __init__(self, app_config):
        """
        Инициализация адаптера.
        
        Args:
            app_config: Flask app.config или ConfigService instance
        """
        # Определяем источник конфига
        if hasattr(app_config, 'use_database'):
            # ConfigService объект
            self.use_database = app_config.use_database
            self.uploads_folder = getattr(app_config, 'uploads_folder', 'uploads')
            self.index_folder = getattr(app_config, 'index_folder', 'index')
        else:
            # Flask app.config словарь
            self.use_database = app_config.get('USE_DATABASE', False)
            self.uploads_folder = app_config.get('UPLOAD_FOLDER', 'uploads')
            self.index_folder = app_config.get('INDEX_FOLDER', 'index')
        
        # Репозитории для БД-режима (ленивая инициализация)
        self._document_repo: Optional[DocumentRepository] = None
        self._chunk_repo: Optional[ChunkRepository] = None
        
        # Флаг для логирования режима (один раз при инициализации)
        mode_name = 'PostgreSQL (БД)' if self.use_database else 'Files (legacy)'
        logger.info(f'DataAccessAdapter инициализирован в режиме: {mode_name}')
    
    # ==========================================================================
    # Внутренние вспомогательные методы
    # ==========================================================================
    
    def _get_document_repo(self, session: Session) -> DocumentRepository:
        """Получить экземпляр DocumentRepository для текущей сессии."""
        return DocumentRepository(session)
    
    def _get_chunk_repo(self, session: Session) -> ChunkRepository:
        """Получить экземпляр ChunkRepository для текущей сессии."""
        return ChunkRepository(session)
    
    def _legacy_index_path(self) -> str:
        """Путь к legacy индексу (_search_index.txt)."""
        # Приоритет: index/_search_index.txt, затем uploads/_search_index.txt
        index_path = os.path.join(self.index_folder, '_search_index.txt')
        if os.path.exists(index_path):
            return index_path
        uploads_index = os.path.join(self.uploads_folder, '_search_index.txt')
        return uploads_index
    
    # ==========================================================================
    # Публичные методы: индексация
    # ==========================================================================
    
    def build_index(self, use_groups: bool = True) -> Tuple[bool, str, Dict[str, int]]:
        """
        Построить поисковый индекс.
        
        В режиме БД: создаёт записи в documents/chunks, дополнительно генерирует
        _search_index.txt для legacy UI.
        
        В режиме файлов: создаёт только _search_index.txt через DocumentProcessor.
        
        Args:
            use_groups: Использовать группировку по папкам в индексе (для legacy UI)
        
        Returns:
            Tuple (success: bool, message: str, char_counts: Dict[str, int])
        """
        try:
            if self.use_database:
                return self._build_index_db(use_groups)
            else:
                return self._build_index_files(use_groups)
        except Exception as e:
            logger.exception('Ошибка построения индекса')
            return False, f'Критическая ошибка: {str(e)}', {}
    
    def _build_index_db(self, use_groups: bool) -> Tuple[bool, str, Dict[str, int]]:
        """
        Построить индекс в режиме БД.
        
        1. Сканирует uploads/
        2. Для каждого файла создаёт запись в documents (если не существует)
        3. Извлекает текст, создаёт chunks
        4. Генерирует embeddings (опционально, если доступны модели)
        5. Создаёт _search_index.txt для обратной совместимости
        """
        logger.info('Построение индекса в БД-режиме...')
        
        # TODO (Шаг 8): полная реализация индексации в БД
        # Временно используем legacy метод для генерации _search_index.txt
        # и дополнительно создадим записи в БД
        
        # Сначала создаём legacy индекс
        dp = DocumentProcessor()
        tmp_index_path = dp.create_search_index(self.uploads_folder, use_groups=use_groups)
        
        # Копируем в index/
        os.makedirs(self.index_folder, exist_ok=True)
        final_index_path = os.path.join(self.index_folder, '_search_index.txt')
        shutil.copyfile(tmp_index_path, final_index_path)
        
        # Парсим char_counts
        char_counts = parse_index_char_counts(final_index_path)
        
        # TODO: добавить создание записей в БД (documents/chunks)
        # with get_db_context() as session:
        #     doc_repo = self._get_document_repo(session)
        #     chunk_repo = self._get_chunk_repo(session)
        #     ... сканирование файлов и создание записей ...
        
        logger.info(f'Индекс создан (БД-режим): {final_index_path}, файлов: {len(char_counts)}')
        return True, 'Индекс построен (БД-режим + legacy файл)', char_counts
    
    def _build_index_files(self, use_groups: bool) -> Tuple[bool, str, Dict[str, int]]:
        """
        Построить индекс в файловом режиме (legacy).
        
        Использует DocumentProcessor для создания _search_index.txt.
        """
        logger.info('Построение индекса в файловом режиме (legacy)...')
        
        dp = DocumentProcessor()
        index_path = dp.create_search_index(self.uploads_folder, use_groups=use_groups)
        
        # Копируем в index/ если индекс создался в uploads/
        if not index_path.startswith(self.index_folder):
            os.makedirs(self.index_folder, exist_ok=True)
            final_index_path = os.path.join(self.index_folder, '_search_index.txt')
            shutil.copyfile(index_path, final_index_path)
            index_path = final_index_path
        
        char_counts = parse_index_char_counts(index_path)
        
        logger.info(f'Индекс создан (legacy): {index_path}, файлов: {len(char_counts)}')
        return True, 'Индекс построен (legacy файл)', char_counts
    
    # ==========================================================================
    # Публичные методы: поиск
    # ==========================================================================
    
    def search_documents(
        self, 
        keywords: List[str], 
        user_id: Optional[int] = None,
        exclude_mode: bool = False,
        context_chars: int = 80
    ) -> List[Dict[str, Any]]:
        """
        Поиск по документам.
        
        В режиме БД: использует ChunkRepository.vector_search или keyword поиск
        В режиме файлов: использует Searcher по _search_index.txt
        
        Args:
            keywords: Список ключевых слов для поиска
            user_id: ID пользователя (для БД-режима, изоляция данных)
            exclude_mode: Режим исключения (найти файлы БЕЗ этих слов)
            context_chars: Количество символов контекста в сниппетах
        
        Returns:
            Список результатов поиска с полями:
            - title: имя файла
            - source: путь к файлу
            - keyword: найденное ключевое слово
            - snippet: фрагмент текста
            - exclude_mode: флаг режима исключения
        """
        if self.use_database:
            return self._search_db(keywords, user_id, exclude_mode, context_chars)
        else:
            return self._search_files(keywords, exclude_mode, context_chars)
    
    def _search_db(
        self, 
        keywords: List[str], 
        user_id: Optional[int],
        exclude_mode: bool,
        context_chars: int
    ) -> List[Dict[str, Any]]:
        """
        Поиск в БД через ChunkRepository.
        
        TODO (Шаг 8): реализовать полноценный поиск через pgvector/keyword search
        Временно используем legacy метод для совместимости.
        """
        logger.info(f'Поиск в БД-режиме: keywords={keywords}, user_id={user_id}, exclude={exclude_mode}')
        
        # TODO: реализовать поиск через ChunkRepository
        # with get_db_context() as session:
        #     chunk_repo = self._get_chunk_repo(session)
        #     if semantic_search:
        #         results = chunk_repo.vector_search(query_embedding, user_id, ...)
        #     else:
        #         results = chunk_repo.keyword_search(keywords, user_id, ...)
        
        # Временно используем legacy поиск
        return self._search_files(keywords, exclude_mode, context_chars)
    
    def _search_files(
        self, 
        keywords: List[str],
        exclude_mode: bool,
        context_chars: int
    ) -> List[Dict[str, Any]]:
        """
        Поиск по _search_index.txt через Searcher (legacy).
        """
        logger.info(f'Поиск в файловом режиме: keywords={keywords}, exclude={exclude_mode}')
        
        index_path = self._legacy_index_path()
        if not os.path.exists(index_path):
            logger.warning(f'Индекс не найден: {index_path}')
            return []
        
        try:
            searcher = Searcher()
            matches = searcher.search(
                index_path, 
                keywords, 
                context=context_chars, 
                exclude_mode=exclude_mode
            )
            return matches
        except Exception as e:
            logger.exception(f'Ошибка поиска по индексу: {e}')
            return []
    
    # ==========================================================================
    # Публичные методы: управление документами
    # ==========================================================================
    
    def get_documents(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Получить список документов пользователя.
        
        В режиме БД: загружает из documents
        В режиме файлов: сканирует uploads/
        
        Args:
            user_id: ID пользователя (для БД-режима)
        
        Returns:
            Список документов с полями: id, filename, size, uploaded_at, status
        """
        if self.use_database:
            return self._get_documents_db(user_id)
        else:
            return self._get_documents_files()
    
    def _get_documents_db(self, user_id: Optional[int]) -> List[Dict[str, Any]]:
        """Получить документы из БД."""
        # TODO (Шаг 8): реализовать
        return []
    
    def _get_documents_files(self) -> List[Dict[str, Any]]:
        """Получить документы из файловой системы."""
        # TODO (Шаг 8): реализовать сканирование uploads/
        return []
    
    def save_document(
        self, 
        user_id: Optional[int],
        filename: str,
        content: bytes,
        content_type: str
    ) -> Optional[int]:
        """
        Сохранить документ.
        
        В режиме БД: создаёт запись в documents
        В режиме файлов: сохраняет в uploads/
        
        Args:
            user_id: ID владельца (для БД-режима)
            filename: Имя файла
            content: Содержимое файла
            content_type: MIME-тип
        
        Returns:
            ID документа (для БД) или None (для файлов)
        """
        if self.use_database:
            return self._save_document_db(user_id, filename, content, content_type)
        else:
            return self._save_document_files(filename, content)
    
    def _save_document_db(
        self, 
        user_id: Optional[int],
        filename: str,
        content: bytes,
        content_type: str
    ) -> Optional[int]:
        """Сохранить документ в БД."""
        # TODO (Шаг 8): реализовать через DocumentRepository
        return None
    
    def _save_document_files(self, filename: str, content: bytes) -> None:
        """Сохранить документ в файловую систему."""
        # TODO (Шаг 8): реализовать сохранение в uploads/
        pass
    
    def delete_document(
        self, 
        user_id: Optional[int],
        doc_id_or_path: Any
    ) -> bool:
        """
        Удалить документ.
        
        В режиме БД: удаляет из documents (cascade на chunks)
        В режиме файлов: удаляет файл из uploads/
        
        Args:
            user_id: ID пользователя (для БД-режима, проверка прав)
            doc_id_or_path: ID документа (БД) или путь к файлу (legacy)
        
        Returns:
            True если удаление успешно, False иначе
        """
        if self.use_database:
            return self._delete_document_db(user_id, doc_id_or_path)
        else:
            return self._delete_document_files(doc_id_or_path)
    
    def _delete_document_db(self, user_id: Optional[int], doc_id: int) -> bool:
        """Удалить документ из БД."""
        # TODO (Шаг 8): реализовать через DocumentRepository
        return False
    
    def _delete_document_files(self, file_path: str) -> bool:
        """Удалить файл из файловой системы."""
        # TODO (Шаг 8): реализовать удаление из uploads/
        return False
