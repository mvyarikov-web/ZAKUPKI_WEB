"""Тесты для оптимизации порядка обработки файлов (increment-013, Этап 3)."""
import os
import pytest
from pathlib import Path
import time


@pytest.mark.timeout(30)
def test_files_sorted_by_extension(tmp_path):
    """Проверка, что файлы обрабатываются в порядке: TXT → DOCX → PDF."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём файлы разных типов
    (root / "file.txt").write_text("Текст", encoding='utf-8')
    (root / "file.pdf").write_bytes(b"%PDF-1.4\n%EOF")
    (root / "file.docx").write_text("Fake DOCX", encoding='utf-8')  # simplified
    
    indexer = Indexer()
    
    # Собираем порядок обработки
    processed_order = []
    for rel_path, abs_path, source in indexer._iter_sources(str(root)):
        ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
        processed_order.append(ext)
    
    # TXT должен быть обработан первым, PDF последним
    txt_idx = processed_order.index('txt')
    pdf_idx = processed_order.index('pdf')
    
    assert txt_idx < pdf_idx, f"TXT должен обрабатываться раньше PDF: {processed_order}"


@pytest.mark.timeout(30)
def test_small_files_before_large(tmp_path):
    """Проверка, что маленькие файлы обрабатываются раньше больших в пределах одной категории."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём PDF файлы разных размеров
    small_pdf = root / "small.pdf"
    large_pdf = root / "large.pdf"
    
    small_pdf.write_bytes(b"%PDF-1.4\nsmall content\n%EOF")
    large_pdf.write_bytes(b"%PDF-1.4\n" + b"X" * 11_000_000 + b"\n%EOF")  # >10MB
    
    indexer = Indexer()
    
    # Собираем порядок обработки
    processed_order = []
    for rel_path, abs_path, source in indexer._iter_sources(str(root)):
        processed_order.append(os.path.basename(rel_path))
    
    # Маленький PDF должен быть обработан первым
    small_idx = processed_order.index('small.pdf')
    large_idx = processed_order.index('large.pdf')
    
    assert small_idx < large_idx, f"Маленькие файлы должны обрабатываться раньше: {processed_order}"


@pytest.mark.timeout(30)
def test_atomic_index_write(tmp_path):
    """Проверка атомарной записи индекса через временный файл."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём простой файл
    (root / "test.txt").write_text("Тестовый контент", encoding='utf-8')
    
    indexer = Indexer()
    index_path = indexer.create_index(str(root))
    
    # Проверяем, что финальный индекс существует
    assert os.path.exists(index_path)
    
    # Проверяем, что временный файл удалён
    temp_path = os.path.join(str(root), "._search_index.tmp")
    assert not os.path.exists(temp_path), "Временный файл не должен оставаться после завершения"
    
    # Проверяем содержимое индекса
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'test.txt' in content
    assert 'Тестовый контент' in content


@pytest.mark.timeout(30)
def test_atomic_write_cleanup_on_error(tmp_path):
    """Проверка, что временный файл удаляется при ошибке индексации."""
    from document_processor.search.indexer import Indexer
    from unittest.mock import patch
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    (root / "test.txt").write_text("Тест", encoding='utf-8')
    
    indexer = Indexer()
    
    # Симулируем ошибку при записи
    with patch.object(indexer, '_write_entry', side_effect=RuntimeError("Test error")):
        try:
            indexer.create_index(str(root))
        except RuntimeError:
            pass  # ожидаем ошибку
    
    # Проверяем, что временный файл удалён
    temp_path = os.path.join(str(root), "._search_index.tmp")
    assert not os.path.exists(temp_path), "Временный файл должен быть удалён при ошибке"


@pytest.mark.timeout(30)
def test_searcher_reads_complete_index(tmp_path):
    """Проверка, что поисковик читает только полный индекс, не частичный."""
    from document_processor.search.indexer import Indexer
    from document_processor.search.searcher import Searcher
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём несколько файлов
    (root / "file1.txt").write_text("Кот играет", encoding='utf-8')
    (root / "file2.txt").write_text("Собака спит", encoding='utf-8')
    
    # Создаём индекс
    indexer = Indexer()
    index_path = indexer.create_index(str(root))
    
    # Поисковик должен найти оба файла
    searcher = Searcher()
    results = searcher.search(index_path, ['кот', 'собака'])
    
    # Должны быть результаты из обоих файлов
    filenames = set()
    for match in results:
        filename = os.path.basename(match['source'])
        filenames.add(filename)
    
    assert 'file1.txt' in filenames
    assert 'file2.txt' in filenames


@pytest.mark.timeout(30)
def test_file_sort_key_priorities():
    """Проверка приоритетов сортировки файлов."""
    from document_processor.search.indexer import Indexer
    
    indexer = Indexer()
    
    # Создаём тестовые записи файлов (ext, name, abs_path, rel_path)
    txt_file = ('txt', 'test.txt', '/tmp/test.txt', 'test.txt')
    pdf_file = ('pdf', 'test.pdf', '/tmp/test.pdf', 'test.pdf')
    docx_file = ('docx', 'test.docx', '/tmp/test.docx', 'test.docx')
    zip_file = ('zip', 'test.zip', '/tmp/test.zip', 'test.zip')
    
    # Получаем ключи сортировки
    txt_key = indexer._file_sort_key(txt_file)
    pdf_key = indexer._file_sort_key(pdf_file)
    docx_key = indexer._file_sort_key(docx_file)
    zip_key = indexer._file_sort_key(zip_file)
    
    # Проверяем порядок приоритетов
    assert txt_key[0] < docx_key[0], "TXT должен иметь более высокий приоритет чем DOCX"
    assert docx_key[0] < pdf_key[0], "DOCX должен иметь более высокий приоритет чем PDF"
    assert pdf_key[0] < zip_key[0], "PDF должен иметь более высокий приоритет чем ZIP"


@pytest.mark.timeout(30)
def test_integration_fast_files_indexed_first(tmp_path):
    """Интеграционный тест: быстрые файлы индексируются первыми."""
    from document_processor.search.indexer import Indexer
    import time
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём файлы разных типов
    (root / "fast.txt").write_text("Быстрый файл", encoding='utf-8')
    (root / "slow.pdf").write_bytes(b"%PDF-1.4\n%EOF")
    
    # Отслеживаем порядок обработки через монкипатчинг
    indexer = Indexer()
    processed = []
    
    original_extract = indexer._extract_text
    def tracked_extract(abs_path, rel_path, source):
        processed.append(os.path.basename(rel_path))
        return original_extract(abs_path, rel_path, source)
    
    indexer._extract_text = tracked_extract
    
    # Создаём индекс
    index_path = indexer.create_index(str(root))
    
    # Проверяем порядок
    txt_idx = processed.index('fast.txt')
    pdf_idx = processed.index('slow.pdf')
    
    assert txt_idx < pdf_idx, f"TXT должен обрабатываться первым: {processed}"


@pytest.mark.timeout(30)
def test_os_replace_atomic_operation(tmp_path):
    """Проверка, что os.replace() обеспечивает атомарность замены."""
    # os.replace() является атомарной операцией на POSIX и Windows
    # Этот тест проверяет, что мы используем именно os.replace, а не другие методы
    
    from document_processor.search.indexer import Indexer
    from unittest.mock import patch, MagicMock
    
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "test.txt").write_text("Тест", encoding='utf-8')
    
    replace_called = [False]
    original_replace = os.replace
    
    def tracked_replace(src, dst):
        replace_called[0] = True
        return original_replace(src, dst)
    
    with patch('os.replace', side_effect=tracked_replace):
        indexer = Indexer()
        indexer.create_index(str(root))
    
    assert replace_called[0], "os.replace() должен быть вызван для атомарной замены"
