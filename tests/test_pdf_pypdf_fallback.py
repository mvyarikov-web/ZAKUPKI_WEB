

def test_extract_pdf_fallback_pypdf(monkeypatch, tmp_path):
    """Тест проверяет, что PDF-извлечение работает через новый модуль pdf_reader.
    
    Обновлено для increment-012: метод _extract_pdf удалён из Indexer,
    вместо него используется PdfReader из модуля pdf_reader.
    """
    # Подготовим фиктивный PDF-файл
    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")

    # Подменяем pdfplumber на фиктивный, который возвращает текст
    try:
        import pdfplumber  # type: ignore
        
        class _DummyPage:
            def extract_text(self):
                return "молоко"
        
        class _DummyPdf:
            def __init__(self, path):
                self.pages = [_DummyPage(), _DummyPage()]
            
            def __enter__(self):
                return self
            
            def __exit__(self, *args):
                pass
        
        monkeypatch.setattr(pdfplumber, "open", _DummyPdf)
    except Exception:
        # Если pdfplumber отсутствует — пропускаем тест
        import pytest
        pytest.skip("pdfplumber не установлен")

    # Вызываем через новый API: PdfReader
    from document_processor.pdf_reader import PdfReader
    
    reader = PdfReader()
    result = reader.read_pdf(str(pdf_path), ocr='off')
    
    # Проверяем, что вернулся текст
    assert "молоко" in result['text']
    # Должно быть объединение страниц
    assert result['text'].count("молоко") >= 2
    assert result['used_extractor'] == 'pdfplumber'
