"""Утилиты для работы с PDF (обратная совместимость).

DEPRECATED: Основная функциональность перенесена в document_processor.pdf_reader
Этот модуль сохраняет алиасы для обратной совместимости со старым кодом.
"""
from flask import make_response, send_file

# Импорты из нового модуля pdf_reader
from .pdf_reader import PdfReader, PdfAnalyzer


def analyze_pdf(path: str):
    """Deprecated: используйте PdfAnalyzer().analyze_pdf() напрямую.
    
    Быстрый анализ PDF: признаки линейности, шифрования, кол-во страниц.
    """
    return PdfAnalyzer().analyze_pdf(path)


def extract_text_pdf(path: str, budget_seconds: float = 5.0):
    """Deprecated: используйте PdfReader().read_pdf() напрямую.
    
    Извлекает текст из PDF, ограничивая общий тайм-аут budget_seconds.
    Возвращает dict: {text, used_extractor, elapsed_ms, attempts}
    """
    result = PdfReader().read_pdf(
        path, ocr='off', budget_seconds=budget_seconds
    )
    return {
        'text': result['text'],
        'used_extractor': result['used_extractor'],
        'elapsed_ms': result['elapsed_ms'],
        'attempts': result['attempts']
    }


def build_pdf_response(path: str, filename: str, inline: bool = True, enable_range: bool = True):
    """Готовит корректный HTTP-ответ для PDF с поддержкой inline/attachment и Range.
    Возвращает flask.Response.
    """
    # conditional=True включает поддержку Range/ETag/Last-Modified у Werkzeug
    resp = make_response(send_file(path, mimetype='application/pdf', as_attachment=not inline, conditional=enable_range))
    # Content-Disposition с UTF-8
    disp = 'inline' if inline else 'attachment'
    try:
        from urllib.parse import quote as _quote
        fname_enc = _quote(filename, safe='')
        resp.headers['Content-Disposition'] = f"{disp}; filename=\"{filename}\"; filename*=UTF-8''{fname_enc}"
    except Exception:
        resp.headers['Content-Disposition'] = f'{disp}; filename="{filename}"'
    # Явно подсвечиваем, что поддерживаем байтовые диапазоны
    if enable_range and 'Accept-Ranges' not in resp.headers:
        resp.headers['Accept-Ranges'] = 'bytes'
    return resp
