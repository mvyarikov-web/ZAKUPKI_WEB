"""Универсальный экстрактор текста (расширенная версия, graceful degrade).

Поддержка:
- TXT (автодетект кодировки)
- JSON, CSV/TSV, XML/HTML (как текст)
- PDF (pdfplumber → pypdf, иначе пустая строка)
- DOCX (python-docx)
- XLSX (openpyxl)
- XLS (xlrd — опционально)

Все тяжёлые импорты обёрнуты в try/except. При любой ошибке возвращается пустая строка.
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
        if ext == 'pdf':
            # pdfplumber → pypdf → ''
            try:
                try:
                    import pdfplumber  # type: ignore
                    text_parts = []
                    with pdfplumber.open(str(p)) as pdf:
                        for page in pdf.pages:
                            t = page.extract_text() or ''
                            if t:
                                text_parts.append(t)
                    return '\n'.join(text_parts)
                except Exception:
                    # fallback на pypdf
                    try:
                        from pypdf import PdfReader  # type: ignore
                        reader = PdfReader(str(p))
                        parts = []
                        for page in reader.pages:
                            t = page.extract_text() or ''
                            if t:
                                parts.append(t)
                        return '\n'.join(parts)
                    except Exception:
                        return ''
            except Exception:
                return ''
        if ext == 'docx':
            try:
                from docx import Document  # type: ignore
                doc = Document(str(p))
                paras = [para.text for para in doc.paragraphs if para.text]
                return '\n'.join(paras)
            except Exception:
                return ''
        if ext == 'doc':
            # Старый формат MS Word через textract (опционально)
            try:
                import textract  # type: ignore
                content_bytes = textract.process(str(p))
                return content_bytes.decode('utf-8', errors='ignore')
            except Exception:
                # Если textract недоступен — пробуем через antiword (системная утилита)
                try:
                    import subprocess
                    result = subprocess.run(
                        ['antiword', str(p)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        return result.stdout
                    return ''
                except Exception:
                    return ''
        if ext == 'xlsx':
            try:
                from openpyxl import load_workbook  # type: ignore
                wb = load_workbook(filename=str(p), data_only=True, read_only=True)
                parts = []
                for ws in wb.worksheets:
                    for row in ws.iter_rows(values_only=True):
                        vals = [str(v) for v in row if v is not None]
                        if vals:
                            parts.append('\t'.join(vals))
                return '\n'.join(parts)
            except Exception:
                return ''
        if ext == 'xls':
            # Опционально через xlrd
            try:
                import xlrd  # type: ignore
                book = xlrd.open_workbook(str(p))
                parts = []
                for si in range(book.nsheets):
                    sh = book.sheet_by_index(si)
                    for ri in range(sh.nrows):
                        row = sh.row_values(ri)
                        vals = [str(v) for v in row if v not in (None, '')]
                        if vals:
                            parts.append('\t'.join(vals))
                return '\n'.join(parts)
            except Exception:
                return ''
        # Неизвестный формат — пусто
        return ''
    except Exception:
        return ''
