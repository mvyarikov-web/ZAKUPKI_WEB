"""
Тесты для проверки корректной обработки специальных символов в содержимом файлов.

Этот тест воспроизводит баг с regex-заменой, когда содержимое файла содержит
символы, которые интерпретируются как обратные ссылки (\1, \2 и т.д.).
"""

import os
import sys
import pytest

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from document_processor.core import DocumentProcessor


def test_index_files_with_backslash_references(tmp_path):
    """
    Тест на обработку файлов с обратными слэшами и цифрами (\1, \2 и т.д.).
    
    Такие символы могут интерпретироваться как обратные ссылки на группы в regex,
    что приводит к ошибке 'invalid group reference'.
    """
    # Создаём тестовую структуру
    test_dir = tmp_path / "test_backslash"
    test_dir.mkdir()
    
    # Создаём файл с содержимым, содержащим \1, \2 и другие потенциально проблемные символы
    test_file = test_dir / "problematic.txt"
    problematic_content = """
    Этот текст содержит обратные ссылки:
    \1 - первая группа
    \2 - вторая группа
    \10 - десятая группа
    Также есть другие спецсимволы: $1, $2, \\g<1>
    И обычный текст: документ, контракт, закупка
    """
    test_file.write_text(problematic_content, encoding='utf-8')
    
    # Запускаем индексацию
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    # Проверяем, что индекс создан
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    # Проверяем, что индекс содержит нужный контент
    with open(index_path, 'r', encoding='utf-8') as f:
        index_content = f.read()
    
    # Проверяем, что проблемные символы присутствуют в индексе
    assert '\\1' in index_content or 'первая группа' in index_content, \
        "Содержимое с обратными ссылками должно быть в индексе"
    
    # Проверяем, что поиск работает
    from document_processor.search.searcher import Searcher
    searcher = Searcher()
    results = searcher.search(index_path, ['документ'], context=80)
    
    assert len(results) > 0, "Поиск должен найти результаты"


def test_index_files_with_dollar_signs(tmp_path):
    """
    Тест на обработку файлов с символами доллара ($1, $2 и т.д.).
    """
    test_dir = tmp_path / "test_dollar"
    test_dir.mkdir()
    
    test_file = test_dir / "prices.txt"
    content = """
    Цены на товары:
    Товар 1: $100
    Товар 2: $200
    Замена: $1 означает первую группу в regex
    Общая сумма: $300
    """
    test_file.write_text(content, encoding='utf-8')
    
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_content = f.read()
    
    assert '$100' in index_content or 'Товар' in index_content, \
        "Содержимое с символами доллара должно быть в индексе"


def test_index_files_with_mixed_special_chars(tmp_path):
    """
    Тест на обработку файлов с различными спецсимволами regex.
    """
    test_dir = tmp_path / "test_mixed"
    test_dir.mkdir()
    
    test_file = test_dir / "mixed.txt"
    content = r"""
    Этот файл содержит множество спецсимволов regex:
    Обратные ссылки: \1, \2, \3, \10
    Доллары: $1, $2, $&, $+
    Скобки: (группа), [класс], {квантификатор}
    Точки и звёздочки: .*? .+ *
    Экранирование: \\ \n \t
    И обычный текст для поиска: контракт, поставщик, спецификация
    """
    test_file.write_text(content, encoding='utf-8')
    
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    # Проверяем поиск
    from document_processor.search.searcher import Searcher
    searcher = Searcher()
    results = searcher.search(index_path, ['контракт'], context=80)
    
    assert len(results) > 0, "Поиск должен работать даже со спецсимволами в индексе"
    assert any('контракт' in r['snippet'].lower() for r in results), \
        "Результаты должны содержать искомое слово"


def test_multiple_files_with_special_chars(tmp_path):
    """
    Тест на индексацию нескольких файлов с различными спецсимволами в разных группах.
    """
    test_dir = tmp_path / "test_multiple"
    test_dir.mkdir()
    
    # Создаём несколько файлов для разных групп скорости
    files_content = [
        ("small1.txt", "Маленький файл с \\1 обратной ссылкой"),
        ("small2.txt", "Ещё один файл с $1 доллар символом"),
        ("medium1.docx", "Средний файл"),  # Это не настоящий docx, но по размеру попадёт в нужную группу
    ]
    
    for filename, content in files_content:
        filepath = test_dir / filename
        # Создаём файл нужного размера
        if 'small' in filename:
            filepath.write_text(content * 10, encoding='utf-8')  # ~400 байт
        else:
            filepath.write_text(content * 5000, encoding='utf-8')  # ~80KB
    
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(test_dir), use_groups=True)
    
    assert os.path.exists(index_path), "Индекс должен быть создан"
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_content = f.read()
    
    # Проверяем, что все группы присутствуют
    assert '<!-- BEGIN_FAST -->' in index_content, "Группа FAST должна быть в индексе"
    
    # Проверяем, что содержимое не повреждено
    assert 'Маленький файл' in index_content or 'обратной ссылкой' in index_content, \
        "Содержимое файлов должно быть в индексе"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
