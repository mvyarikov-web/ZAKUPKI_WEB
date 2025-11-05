"""Универсальный экстрактор текста (минимальная версия).

Поддержка:
- TXT (автодетект кодировки)
- JSON, CSV/TSV, XML/HTML (как текст)

Best-effort заглушки:
- PDF/DOCX/XLS/XLSX — возвращают пустую строку, чтобы не падать без системных зависимостей.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import chardet  # type: ignore


def _read_text_with_encoding(path: Path) -> str:
    data = path.read_bytes()
    guess = chardet.detect(data) or {}
    enc = guess.get('encoding') or 'utf-8'
    for codec in (enc, 'utf-8', 'cp1251', 'cp866', 'latin-1'):
        try:
            return data.decode(codec, errors='ignore')
        except Exception:
            continue
    return ''


def extract_text(file_path: str) -> str:
    """Вернуть извлечённый текст из файла. Ошибки глушатся (graceful degrade).

    Args:
        file_path: Путь к файлу

    Returns:
        str: Текстовое содержимое (или пустая строка)
    """
    try:
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return ''
        ext = p.suffix.lower().lstrip('.')
        if ext in {'txt', 'json', 'csv', 'tsv', 'xml', 'html', 'htm'}:
            return _read_text_with_encoding(p)
        # Для тяжёлых форматов пока возвращаем пустую строку, чтобы не падало
        if ext in {'pdf', 'doc', 'docx', 'xls', 'xlsx'}:
            return ''
        # Неизвестный формат — пусто
        return ''
    except Exception:
        return ''
