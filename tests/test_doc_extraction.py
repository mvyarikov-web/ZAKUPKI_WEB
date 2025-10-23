"""
Тест извлечения текста из устаревших DOC файлов.
Проверяет качество извлечения и поддержку различных методов (antiword, textract, fallback).
"""
import pytest
import os
import tempfile
from document_processor.search.indexer import Indexer


def test_doc_extraction_quality():
    """Проверка качества извлечения текста из DOC файла."""
    indexer = Indexer()
    
    # Для реального теста нужен настоящий DOC файл
    # Здесь проверяем, что метод не падает на несуществующем файле
    fake_doc_path = "/tmp/nonexistent.doc"
    
    # Должен вернуть пустую строку без исключений
    text = indexer._extract_doc(fake_doc_path)
    assert isinstance(text, str)
    assert text == ""


def test_doc_extraction_fallback_method():
    """Проверка работы fallback метода для DOC (бинарный парсинг)."""
    indexer = Indexer()
    
    # Создаём простой "псевдо-DOC" файл с текстом в кодировке cp1251
    test_text = "Тестовый текст на русском языке"
    
    with tempfile.NamedTemporaryFile(suffix='.doc', delete=False, mode='wb') as f:
        # Записываем текст в cp1251 с добавлением ASCII символов (имитация DOC)
        # В реальном DOC много бинарных данных, но для теста достаточно текста
        fake_doc_content = b'\x00\x01\x02' + test_text.encode('cp1251') + b'\x00\x01\x02'
        f.write(fake_doc_content)
        temp_path = f.name
    
    try:
        # Извлекаем текст
        text = indexer._extract_doc(temp_path)
        
        # Проверяем, что хотя бы часть текста распознана
        # (точное совпадение не гарантируется из-за бинарных префиксов)
        assert isinstance(text, str)
        assert len(text) > 0
        
        # Проверяем наличие русских символов
        has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in text)
        assert has_cyrillic, f"Не найдены кириллические символы в извлечённом тексте: {text[:100]}"
        
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_antiword_availability():
    """Проверка доступности antiword (необязательный тест)."""
    import subprocess
    
    try:
        result = subprocess.run(
            ['antiword', '-v'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            print(f"\n✅ antiword установлен: {result.stdout.strip()}")
        else:
            print(f"\n⚠️ antiword вернул код {result.returncode}")
    except FileNotFoundError:
        print("\n⚠️ antiword не установлен (необязательная зависимость)")
        pytest.skip("antiword не установлен")
    except Exception as e:
        print(f"\n⚠️ Ошибка проверки antiword: {e}")
        pytest.skip(f"Ошибка проверки antiword: {e}")


def test_textract_availability():
    """Проверка доступности textract (необязательный тест)."""
    try:
        import textract
        print(f"\n✅ textract установлен: версия {textract.__version__ if hasattr(textract, '__version__') else 'неизвестна'}")
    except ImportError:
        print("\n⚠️ textract не установлен (необязательная зависимость)")
        pytest.skip("textract не установлен")


def test_doc_extraction_methods_priority():
    """Проверка приоритета методов извлечения DOC."""
    indexer = Indexer()
    
    # Проверяем, что методы существуют
    assert hasattr(indexer, '_try_antiword')
    assert hasattr(indexer, '_try_textract')
    assert hasattr(indexer, '_try_docx_for_doc')
    assert hasattr(indexer, '_extract_doc')
    
    # Все методы должны возвращать строки
    fake_path = "/tmp/nonexistent.doc"
    
    result1 = indexer._try_antiword(fake_path)
    assert isinstance(result1, str)
    
    result2 = indexer._try_textract(fake_path)
    assert isinstance(result2, str)
    
    result3 = indexer._try_docx_for_doc(fake_path)
    assert isinstance(result3, str)


@pytest.mark.skipif(
    not os.path.exists('/usr/local/bin/antiword') and not os.path.exists('/usr/bin/antiword'),
    reason="antiword не установлен"
)
def test_doc_with_antiword_real():
    """Тест извлечения с помощью antiword (если установлен).
    
    Для полноценного теста требуется настоящий DOC файл.
    """
    # Этот тест требует реальный DOC файл
    # В продакшене можно добавить тестовый DOC в fixtures/
    pytest.skip("Требуется реальный DOC файл для теста")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
