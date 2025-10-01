"""Тест для проверки отсутствия дублирования результатов поиска."""
import pytest
import tempfile
from pathlib import Path
from document_processor.search.searcher import Searcher


def test_searcher_no_duplicates():
    """Проверяем, что Searcher не возвращает дублирующиеся результаты."""
    # Создаём тестовый индекс с повторяющимся словом
    test_index_content = """========================================
ЗАГОЛОВОК: Тестовый документ
Формат: TXT | Символов: 100 | Дата: 2025-01-01
Источник: test.txt
========================================
Этот документ содержит слово договор несколько раз.
Первый договор в начале. Второй договор в середине.
Третий до-говор с разделителем. Четвёртый д о г о в о р с пробелами.
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(test_index_content)
        index_path = f.name
    
    try:
        searcher = Searcher()
        results = searcher.search(index_path, ['договор'], context=20)
        
        # Проверяем, что нет дубликатов по позиции
        positions = set()
        for result in results:
            key = (result.get('title'), result.get('keyword'), result.get('position'))
            assert key not in positions, f"Найден дубликат: {key}"
            positions.add(key)
        
        # Должно быть найдено как минимум 4 уникальных вхождения
        assert len(results) >= 4, f"Ожидалось минимум 4 результата, получено {len(results)}"
        
        # Все результаты должны содержать ключевое слово (в любом виде)
        for result in results:
            assert result.get('keyword') == 'договор'
            snippet_lower = result.get('snippet', '').lower()
            # Проверяем, что в сниппете есть либо "договор", либо его разделённая версия
            has_keyword = ('договор' in snippet_lower or 
                          'до-говор' in snippet_lower or
                          'д о г о в о р' in snippet_lower)
            assert has_keyword, f"Ключевое слово не найдено в сниппете: {snippet_lower}"
        
        print(f"✓ Тест пройден: найдено {len(results)} уникальных результатов")
        
    finally:
        Path(index_path).unlink()


def test_searcher_tolerant_search_no_duplicates():
    """Проверяем, что толерантный поиск не создаёт дубликаты с обычным поиском."""
    test_index_content = """========================================
ЗАГОЛОВОК: PDF документ с разделителями
Формат: PDF | Символов: 200 | Дата: 2025-01-01  
Источник: test.pdf
========================================
Обычное слово: тест
Слово с разделителями: т е с т
Слово с дефисами: те-ст
Комбинированное: тест и т е с т рядом
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(test_index_content)
        index_path = f.name
    
    try:
        searcher = Searcher()
        results = searcher.search(index_path, ['тест'], context=15)
        
        # Группируем по позициям для проверки дубликатов
        positions = {}
        for result in results:
            pos = result.get('position')
            if pos in positions:
                pytest.fail(f"Дубликат на позиции {pos}: {result}")
            positions[pos] = result
        
        # Проверяем, что найдены разные вхождения
        assert len(results) >= 3, f"Ожидалось минимум 3 результата, получено {len(results)}"
        
        print(f"✓ Толерантный поиск: найдено {len(results)} уникальных результатов")
        
    finally:
        Path(index_path).unlink()


if __name__ == "__main__":
    test_searcher_no_duplicates()
    test_searcher_tolerant_search_no_duplicates()
    print("Все тесты на отсутствие дубликатов пройдены ✓")