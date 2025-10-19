from __future__ import annotations
import os
from typing import List, Dict, Optional
from .search.indexer import Indexer
from .search.searcher import Searcher

class DocumentProcessor:
    """High-level orchestration for indexing and searching documents.

    API:
      - create_search_index(root_folder) -> path to _search_index.txt
      - search_keywords(index_path, keywords, context=80) -> list of matches
      - get_file_stats(source) -> dict (stub for now)
    """

    def __init__(self, *, max_depth: int = 10, archive_depth: int = 0):
        self.max_depth = max_depth
        self.archive_depth = archive_depth
        self.indexer = Indexer(max_depth=max_depth, archive_depth=archive_depth)
        self.searcher = Searcher()

    def create_search_index(self, root_folder: str, use_groups: bool = False) -> str:
        """Создаёт поисковый индекс для файлов в указанной папке.
        
        Args:
            root_folder: корневая папка для индексации
            use_groups: если True, использует групповую индексацию (increment-014)
        
        Returns:
            путь к созданному индексу
        """
        if not os.path.isdir(root_folder):
            raise ValueError(f"Folder not found: {root_folder}")
        return self.indexer.create_index(root_folder, use_groups=use_groups)

    def search_keywords(self, index_path: str, keywords: List[str], context: int = 80) -> List[Dict]:
        return self.searcher.search(index_path, keywords, context=context)

    def get_file_stats(self, source: str) -> Dict:
        # TODO: wire to index metadata store
        return {}
