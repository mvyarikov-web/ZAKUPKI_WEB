"""Модуль анализа текста по сводному индексу."""
from document_processor.analysis.extractor import Extractor
from document_processor.analysis.schemas import (
    Procurement,
    Item,
    Party,
    Address,
    Terms,
    AnalysisResult
)

__all__ = [
    'Extractor',
    'Procurement',
    'Item',
    'Party',
    'Address',
    'Terms',
    'AnalysisResult'
]
