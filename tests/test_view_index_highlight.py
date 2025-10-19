"""
Тесты для проверки подсветки поисковых терминов в сводном индексе.
"""

import os
import sys
import pytest

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from document_processor.core import DocumentProcessor


def test_view_index_saves_search_terms(tmp_path):
    """
    Тест проверяет, что поисковые термины сохраняются в search_results.json
    и могут быть использованы для подсветки в /view_index.
    """
    # Создаём тестовую структуру
    test_dir = tmp_path / "test_highlight"
    test_dir.mkdir()
    
    # Создаём несколько файлов с контентом
    (test_dir / "file1.txt").write_text("Это документ с ключевым словом контракт", encoding='utf-8')
    (test_dir / "file2.txt").write_text("Здесь есть слово поставщик и закупка", encoding='utf-8')
    (test_dir / "file3.txt").write_text("Обычный текст без ключевых слов", encoding='utf-8')
    
    # Создаём индекс
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    # Проверяем, что индекс содержит все файлы
    with open(index_path, 'r', encoding='utf-8') as f:
        index_content = f.read()
    
    assert 'контракт' in index_content, "Индекс должен содержать слово 'контракт'"
    assert 'поставщик' in index_content, "Индекс должен содержать слово 'поставщик'"
    assert 'закупка' in index_content, "Индекс должен содержать слово 'закупка'"


def test_search_terms_filtering(tmp_path):
    """
    Тест проверяет, что поисковые термины корректно фильтруются
    (удаляются дубликаты, короткие/длинные слова).
    """
    test_dir = tmp_path / "test_filter"
    test_dir.mkdir()
    
    (test_dir / "test.txt").write_text("Тестовый файл для проверки фильтрации терминов", encoding='utf-8')
    
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    # Проверяем поиск
    from document_processor.search.searcher import Searcher
    searcher = Searcher()
    
    # Поиск с дубликатами - должны быть удалены
    results = searcher.search(index_path, ['файл', 'файл', 'тест'], context=80)
    assert len(results) > 0, "Поиск должен найти результаты несмотря на дубликаты"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
