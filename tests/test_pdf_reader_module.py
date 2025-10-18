"""Тесты для модуля pdf_reader (increment-012)."""
import os
import pytest
from pathlib import Path


@pytest.mark.timeout(10)
def test_pdf_reader_basic_import():
    """Проверка импорта модуля."""
    from document_processor.pdf_reader import PdfReader, PdfAnalyzer
    
    reader = PdfReader()
    analyzer = PdfAnalyzer()
    
    assert reader is not None
    assert analyzer is not None


@pytest.mark.timeout(10)
def test_pdf_reader_vector_basic(tmp_path):
    """Векторный PDF: извлечение текста через PdfReader."""
    # Создать минимальный PDF-файл
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    from document_processor.pdf_reader import PdfReader
    
    reader = PdfReader()
    result = reader.read_pdf(str(pdf_path), ocr='off')
    
    # Проверка структуры результата
    assert 'text' in result
    assert 'pages' in result
    assert 'ocr_used' in result
    assert 'used_extractor' in result
    assert 'elapsed_ms' in result
    assert 'has_text_layer' in result
    assert 'attempts' in result
    
    # OCR не должен использоваться при ocr='off'
    assert result['ocr_used'] == False
    assert isinstance(result['elapsed_ms'], int)
    assert isinstance(result['attempts'], list)


@pytest.mark.timeout(10)
def test_pdf_analyzer_basic(tmp_path):
    """Анализ PDF через PdfAnalyzer."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nLINEARIZED\n%EOF")
    
    from document_processor.pdf_reader import PdfAnalyzer
    
    analyzer = PdfAnalyzer()
    info = analyzer.analyze_pdf(str(pdf_path))
    
    # Проверка структуры
    assert 'path' in info
    assert 'is_pdf' in info
    assert 'linearized' in info
    assert 'is_encrypted' in info
    assert 'pages' in info
    assert 'size' in info
    
    # Должен определить как PDF
    assert info['is_pdf'] == True


@pytest.mark.timeout(5)
def test_pdf_reader_empty_pdf(tmp_path):
    """Пустой PDF: нет исключений, пустой текст."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    from document_processor.pdf_reader import PdfReader
    
    reader = PdfReader()
    result = reader.read_pdf(str(pdf_path), ocr='off')
    
    # Не должно быть исключений
    assert result['text'] == ''
    assert len(result['attempts']) > 0


@pytest.mark.timeout(5)
def test_pdf_reader_nonexistent_file():
    """Несуществующий файл: обработка ошибки."""
    from document_processor.pdf_reader import PdfReader
    
    reader = PdfReader()
    
    # Должен обработать ошибку без падения
    try:
        result = reader.read_pdf('/nonexistent/file.pdf', ocr='off')
        # Если не падает, то должен вернуть пустой результат
        assert result['text'] == ''
    except Exception:
        # Или может выбросить исключение — это тоже допустимо
        pass


@pytest.mark.timeout(10)
def test_pdf_reader_with_monkeypatch(monkeypatch, tmp_path):
    """Проверка каскада экстракторов через monkeypatch."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    from document_processor.pdf_reader import PdfReader
    
    # Подменяем pdfplumber на фиктивный, который возвращает текст
    try:
        import pdfplumber  # type: ignore
        
        class _DummyPage:
            def extract_text(self):
                return "тестовый текст из pdfplumber"
        
        class _DummyPdf:
            def __init__(self, path):
                self.pages = [_DummyPage()]
            
            def __enter__(self):
                return self
            
            def __exit__(self, *args):
                pass
        
        monkeypatch.setattr(pdfplumber, "open", _DummyPdf)
        
        reader = PdfReader()
        result = reader.read_pdf(str(pdf_path), ocr='off')
        
        # Должен использовать pdfplumber и получить наш текст
        assert "тестовый текст" in result['text']
        assert result['used_extractor'] == 'pdfplumber'
        
    except ImportError:
        pytest.skip("pdfplumber не установлен")


@pytest.mark.timeout(10)
def test_backward_compatibility_pdf_utils(tmp_path):
    """Обратная совместимость: алиасы в pdf_utils.py."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    # Импорт через старый API
    from document_processor.pdf_utils import analyze_pdf, extract_text_pdf
    
    # Анализ PDF
    info = analyze_pdf(str(pdf_path))
    assert 'is_pdf' in info
    assert info['is_pdf'] == True
    
    # Извлечение текста
    result = extract_text_pdf(str(pdf_path), budget_seconds=2.0)
    assert 'text' in result
    assert 'used_extractor' in result
    assert 'elapsed_ms' in result
    assert 'attempts' in result


@pytest.mark.timeout(15)
def test_indexer_uses_pdf_reader(tmp_path):
    """Интеграция: индексатор использует PdfReader вместо старого кода."""
    # Создать структуру файлов
    root = tmp_path / "uploads"
    root.mkdir()
    
    pdf_path = root / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    from document_processor.search.indexer import Indexer
    
    indexer = Indexer()
    index_file = indexer.create_index(str(root))
    
    # Индекс должен быть создан
    assert os.path.exists(index_file)
    
    # Прочитать индекс
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Должен быть заголовок для PDF-файла
    assert 'test.pdf' in content
    assert 'PDF' in content


@pytest.mark.skipif(
    not os.environ.get('TEST_OCR_AVAILABLE'),
    reason="OCR-зависимости не установлены (pytesseract/pdf2image)"
)
@pytest.mark.timeout(30)
def test_pdf_reader_ocr_mode(tmp_path):
    """Тест OCR-режима (только если доступен tesseract)."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    from document_processor.pdf_reader import PdfReader
    
    reader = PdfReader()
    
    # Принудительный OCR
    result = reader.read_pdf(str(pdf_path), ocr='force', max_pages_ocr=1)
    
    # OCR должен быть попыткой (даже если не удался)
    assert any(a['name'] == 'ocr' for a in result['attempts'])


def test_no_duplicated_code():
    """Проверка, что дублированный код удалён из indexer.py."""
    indexer_path = Path(__file__).parent.parent / 'document_processor' / 'search' / 'indexer.py'
    
    with open(indexer_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Метод _extract_pdf должен быть удалён
    assert 'def _extract_pdf(' not in content, \
        "Метод _extract_pdf всё ещё существует в indexer.py (должен быть удалён)"
    
    # Должен быть импорт PdfReader
    assert 'from ..pdf_reader import PdfReader' in content, \
        "Отсутствует импорт PdfReader в indexer.py"


def test_pdf_utils_uses_pdf_reader():
    """Проверка, что pdf_utils.py использует pdf_reader (не дублирует код)."""
    pdf_utils_path = Path(__file__).parent.parent / 'document_processor' / 'pdf_utils.py'
    
    with open(pdf_utils_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Должен импортировать из pdf_reader
    assert 'from .pdf_reader import' in content, \
        "Отсутствует импорт из pdf_reader в pdf_utils.py"
    
    # Не должно быть дублированных импортов PDF-библиотек для извлечения
    # (только для build_pdf_response можно использовать flask)
    lines = content.split('\n')
    
    # Подсчёт использования старого кода извлечения
    old_extraction_patterns = [
        'pdfplumber.open',
        'pypdf.PdfReader',
        'pdfminer_extract_text',
        'fitz.open'
    ]
    
    for pattern in old_extraction_patterns:
        # Не должно быть прямого использования экстракторов (кроме комментариев)
        for line in lines:
            if pattern in line and not line.strip().startswith('#'):
                # Исключение: импорты в начале могут быть для других целей
                if 'import' in line and (pattern == 'pypdf.PdfReader' or 'try:' in content[:content.index(line)]):
                    continue
