"""Тесты для режима исключения (exclude_mode) в поиске."""
import os
from pathlib import Path
import pytest
from document_processor import DocumentProcessor
from document_processor.search.searcher import Searcher


@pytest.fixture
def test_files(tmp_path):
    """Создаёт набор тестовых файлов."""
    # Файл 1: содержит слово "договор"
    file1 = tmp_path / "file1.txt"
    file1.write_text("Это важный договор о поставке товаров.", encoding="utf-8")
    
    # Файл 2: содержит слово "контракт"
    file2 = tmp_path / "file2.txt"
    file2.write_text("Контракт на оказание услуг подписан.", encoding="utf-8")
    
    # Файл 3: не содержит ни одного из искомых слов
    file3 = tmp_path / "file3.txt"
    file3.write_text("Обычный текстовый файл без ключевых слов.", encoding="utf-8")
    
    # Файл 4: пустой файл
    file4 = tmp_path / "file4.txt"
    file4.write_text("", encoding="utf-8")
    
    return tmp_path


def test_exclude_mode_basic(test_files):
    """Тест базового режима исключения: файлы НЕ содержащие ключевое слово."""
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_files))
    
    searcher = Searcher()
    results = searcher.search(index_path, ["договор"], exclude_mode=True)
    
    # Должны найти файлы, которые НЕ содержат слово "договор"
    # file1.txt содержит "договор" - НЕ должен быть в результатах
    # file2.txt, file3.txt, file4.txt НЕ содержат "договор" - должны быть в результатах
    assert len(results) >= 2  # как минимум file2 и file3
    
    titles = [r.get('title', '') for r in results]
    # file1.txt не должен быть в результатах
    assert not any('file1.txt' in t for t in titles)
    # file2.txt и file3.txt должны быть в результатах
    assert any('file2.txt' in t for t in titles)
    assert any('file3.txt' in t for t in titles)


def test_exclude_mode_multiple_keywords(test_files):
    """Тест режима исключения с несколькими ключевыми словами."""
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_files))
    
    searcher = Searcher()
    results = searcher.search(index_path, ["договор", "контракт"], exclude_mode=True)
    
    # Должны найти файлы, которые НЕ содержат ни "договор", ни "контракт"
    # file1.txt содержит "договор" - НЕ должен быть в результатах
    # file2.txt содержит "контракт" - НЕ должен быть в результатах
    # file3.txt НЕ содержит ни того, ни другого - должен быть в результатах
    titles = [r.get('title', '') for r in results]
    
    assert not any('file1.txt' in t for t in titles)
    assert not any('file2.txt' in t for t in titles)
    assert any('file3.txt' in t for t in titles)


def test_exclude_mode_snippet_from_start(test_files):
    """Тест что в режиме исключения сниппет берётся с начала документа."""
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_files))
    
    searcher = Searcher()
    results = searcher.search(index_path, ["договор"], exclude_mode=True, context=50)
    
    # Проверяем, что сниппеты содержат текст с начала файлов
    for r in results:
        title = r.get('title', '')
        snippet = r.get('snippet', '')
        
        if 'file3.txt' in title:
            # Сниппет должен содержать начало текста file3.txt (после маркера "НАЧАЛО ДОКУМЕНТА")
            # Индексатор добавляет маркер <<< НАЧАЛО ДОКУМЕНТА >>>, но содержимое должно быть после него
            assert 'Обычный' in snippet or 'НАЧАЛО ДОКУМЕНТА' in snippet
        
        # В режиме exclude_mode keyword должен быть пустым
        assert r.get('keyword', '') == ''
        # Должен быть флаг exclude_mode
        assert r.get('exclude_mode') is True


def test_normal_mode_still_works(test_files):
    """Проверка что обычный режим (exclude_mode=False) продолжает работать."""
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_files))
    
    searcher = Searcher()
    results = searcher.search(index_path, ["договор"], exclude_mode=False)
    
    # В обычном режиме должны найти файл, который СОДЕРЖИТ слово "договор"
    assert len(results) > 0
    titles = [r.get('title', '') for r in results]
    assert any('file1.txt' in t for t in titles)
    
    # Проверяем, что у результатов есть keyword
    for r in results:
        if 'file1.txt' in r.get('title', ''):
            assert r.get('keyword', '').lower() == 'договор'
            assert 'exclude_mode' not in r or r.get('exclude_mode') is False


def test_exclude_mode_empty_result(test_files):
    """Тест когда все файлы содержат искомое слово - результат должен быть пустым."""
    # Создаём файлы, все содержащие слово "тест"
    test_dir = test_files / "subdir"
    test_dir.mkdir()
    
    (test_dir / "a.txt").write_text("Это тест 1", encoding="utf-8")
    (test_dir / "b.txt").write_text("Это тест 2", encoding="utf-8")
    
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir))
    
    searcher = Searcher()
    results = searcher.search(index_path, ["тест"], exclude_mode=True)
    
    # Все файлы содержат "тест", поэтому результатов не должно быть
    assert len(results) == 0
