"""Исключения модуля pdf_reader."""


class PdfReadError(Exception):
    """Базовая ошибка чтения PDF."""
    pass


class OcrNotAvailableError(PdfReadError):
    """OCR недоступен (отсутствуют зависимости)."""
    pass
