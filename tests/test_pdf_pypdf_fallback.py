import os
import types


def test_extract_pdf_fallback_pypdf(monkeypatch, tmp_path):
    # Подготовим фиктивный PDF-файл (содержимое неважно для подменяемого ридера)
    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")

    # Импортируем индексатор
    from document_processor.search.indexer import Indexer
    idx = Indexer()

    # 1) Ломаем pdfplumber.open, чтобы перейти в фолбэк
    try:
        import pdfplumber  # type: ignore
        def _broken_open(*args, **kwargs):
            raise RuntimeError("forced pdfplumber failure")
        monkeypatch.setattr(pdfplumber, "open", _broken_open)
    except Exception:
        # Если pdfplumber отсутствует — это тоже ок, фолбэк сработает
        pass

    # 2) Подменяем pypdf.PdfReader на фиктивный, который возвращает ожидаемый текст
    import pypdf  # type: ignore

    class _DummyPage:
        def extract_text(self):
            return "молоко"

    class _DummyReader:
        def __init__(self, *_a, **_k):
            self.pages = [_DummyPage(), _DummyPage()]

    monkeypatch.setattr(pypdf, "PdfReader", _DummyReader)

    # 3) Вызываем приватный метод извлечения PDF и проверяем, что вернулся текст
    text = idx._extract_pdf(str(pdf_path))
    assert "молоко" in text
    # Должно быть объединение страниц через перевод строки
    assert text.count("молоко") >= 2
