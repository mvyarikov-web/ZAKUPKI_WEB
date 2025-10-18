"""Модуль чтения PDF-документов (векторные и сканы).

Объединяет логику из pdf_utils.py и indexer._extract_pdf() в единый модуль.
Поддерживает автоматическое определение типа PDF и извлечение текста через каскад экстракторов.
"""

from .reader import PdfReader
from .analyzer import PdfAnalyzer
from .exceptions import PdfReadError, OcrNotAvailableError

__all__ = [
    'PdfReader',
    'PdfAnalyzer',
    'PdfReadError',
    'OcrNotAvailableError',
]
