from __future__ import annotations
import os
import io
import zipfile
import tempfile
import datetime
from datetime import datetime
from typing import Iterable, Tuple, List, Optional, Any
import logging

# Разделитель заголовков в индексе
HEADER_BAR = "===============================" 
# Маркеры начала и конца документа
DOC_START_MARKER = "<<< НАЧАЛО ДОКУМЕНТА >>>"
DOC_END_MARKER = "<<< КОНЕЦ ДОКУМЕНТА >>>"
SUPPORTED_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "txt", "zip", "rar", "html", "htm", "csv", "tsv", "xml", "json"}
DOC_EXTS = {"doc", "docx"}

class Indexer:
    def __init__(self, *, max_depth: int = 10, archive_depth: int = 0):
        self.max_depth = max_depth
        self.archive_depth = archive_depth
        self._temp_paths: List[str] = []
        self._log = logging.getLogger(__name__)

    def create_index(self, root_folder: str) -> str:
        index_path = os.path.join(root_folder, "_search_index.txt")
        self._log.info("Индексация начата: root=%s -> %s", root_folder, index_path)
        try:
            with io.open(index_path, "w", encoding="utf-8") as out:
                for rel_path, abs_path, source in self._iter_sources(root_folder):
                    text, meta = self._extract_text(abs_path, rel_path, source)
                    self._write_entry(out, rel_path=source, text=text, meta=meta)
            self._log.info("Индексация завершена: %s", index_path)
            return index_path
        finally:
            self._cleanup_temp_paths()

    def _iter_sources(self, root_folder: str) -> Iterable[Tuple[str, str, str]]:
        # Walk directories recursively
        for dirpath, dirnames, filenames in os.walk(root_folder):
            # Optionally limit depth
            rel_dir = os.path.relpath(dirpath, root_folder)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth > self.max_depth:
                continue
            for name in sorted(filenames):
                # Пропускаем временные файлы Office (обычно начинаются с ~$ или $)
                if name.startswith("~$") or name.startswith("$"):
                    continue
                # Пропускаем сам сводный индекс
                if name == "_search_index.txt":
                    continue
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext in SUPPORTED_EXT:
                    abs_path = os.path.join(dirpath, name)
                    rel_path = os.path.normpath(os.path.join(rel_dir, name)) if rel_dir != "." else name
                    if ext in {"zip", "rar"}:
                        for v_rel, v_abs, v_source in self._iter_archive(abs_path, rel_path, ext, current_depth=0):
                            yield v_rel, v_abs, v_source
                    else:
                        yield rel_path, abs_path, rel_path

    def _iter_archive(self, archive_path: str, rel_path: str, kind: str, current_depth: int = 0) -> Iterable[Tuple[str, str, str]]:
        # Extract supported files from archive into temp files and yield paths
        # FR-008: Поддержка вложенных архивов с учетом archive_depth
        entries: List[Tuple[str, str, str]] = []
        
        # Проверяем глубину вложенности архивов
        if current_depth > self.archive_depth:
            self._log.info("Пропуск вложенного архива (превышена глубина %d): %s", self.archive_depth, rel_path)
            return []
        
        try:
            if kind == "zip":
                try:
                    with zipfile.ZipFile(archive_path) as z:
                        for zi in z.infolist():
                            if zi.is_dir():
                                continue
                            inner_name = zi.filename
                            ext = inner_name.rsplit(".", 1)[-1].lower() if "." in inner_name else ""
                            if ext and ext in SUPPORTED_EXT:
                                # FR-008: Обработка вложенных архивов
                                if ext in {"zip", "rar"} and current_depth < self.archive_depth:
                                    data = z.read(zi)
                                    tmp_path = self._write_temp_file(data, suffix=f".{ext}")
                                    nested_rel = f"{rel_path}!/{inner_name}"
                                    # Рекурсивно обрабатываем вложенный архив
                                    for nested_v_rel, nested_v_abs, nested_v_source in self._iter_archive(
                                        tmp_path, nested_rel, ext, current_depth + 1
                                    ):
                                        entries.append((nested_v_rel, nested_v_abs, nested_v_source))
                                elif ext not in {"zip", "rar"}:
                                    # Обычный файл внутри архива
                                    data = z.read(zi)
                                    tmp_path = self._write_temp_file(data, suffix=f".{ext}")
                                    v_rel = f"{rel_path}!/{inner_name}"
                                    v_source = f"zip://{rel_path}!/{inner_name}"
                                    entries.append((v_rel, tmp_path, v_source))
                except zipfile.BadZipFile:
                    self._log.warning("Повреждённый ZIP архив: %s", rel_path)
                    return []
            elif kind == "rar":
                try:
                    import rarfile  # type: ignore
                    with rarfile.RarFile(archive_path) as rf:
                        for ri in rf.infolist():
                            if ri.isdir():
                                continue
                            inner_name = ri.filename
                            ext = inner_name.rsplit(".", 1)[-1].lower() if "." in inner_name else ""
                            if ext and ext in SUPPORTED_EXT:
                                # FR-008: Обработка вложенных архивов
                                if ext in {"zip", "rar"} and current_depth < self.archive_depth:
                                    with rf.open(ri) as rfp:
                                        data = rfp.read()
                                    tmp_path = self._write_temp_file(data, suffix=f".{ext}")
                                    nested_rel = f"{rel_path}!/{inner_name}"
                                    # Рекурсивно обрабатываем вложенный архив
                                    for nested_v_rel, nested_v_abs, nested_v_source in self._iter_archive(
                                        tmp_path, nested_rel, ext, current_depth + 1
                                    ):
                                        entries.append((nested_v_rel, nested_v_abs, nested_v_source))
                                elif ext not in {"zip", "rar"}:
                                    # Обычный файл внутри архива
                                    with rf.open(ri) as rfp:
                                        data = rfp.read()
                                    tmp_path = self._write_temp_file(data, suffix=f".{ext}")
                                    v_rel = f"{rel_path}!/{inner_name}"
                                    v_source = f"rar://{rel_path}!/{inner_name}"
                                    entries.append((v_rel, tmp_path, v_source))
                except Exception:
                    # rar unsupported on system or corrupted: skip gracefully
                    self._log.warning("RAR не поддержан системой или ошибка чтения: %s", rel_path)
                    return []
        except Exception:
            self._log.exception("Ошибка при чтении архива: %s", rel_path)
            return []
        
        # FR-007: Логирование событий индексации архивов
        if entries:
            self._log.info("Обработан архив %s: извлечено %d файлов (глубина %d)", rel_path, len(entries), current_depth)
        
        return entries

    def _write_temp_file(self, data: bytes, suffix: str = "") -> str:
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        self._temp_paths.append(tmp_path)
        return tmp_path

    def _cleanup_temp_paths(self):
        for p in self._temp_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        self._temp_paths.clear()

    def _extract_text(self, abs_path: str, rel_path: str, source: str):
        ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
        text = ""
        ocr_used = False
        try:
            if ext == "txt":
                text = self._read_text_with_encoding(abs_path)
            elif ext in {"html", "htm"}:
                raw = self._read_text_with_encoding(abs_path)
                text = self._html_to_text(raw)
            elif ext in {"xml", "json"}:
                text = self._read_text_with_encoding(abs_path)
            elif ext in {"csv", "tsv"}:
                sep = "," if ext == "csv" else "\t"
                try:
                    import csv
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        rows = list(csv.reader(f, delimiter=sep))
                    text = "\n".join([" | ".join(row) for row in rows])
                except Exception:
                    text = self._read_text_with_encoding(abs_path)
            elif ext == "pdf":
                # FR-004: Оптимизация - сначала пробуем pdfplumber
                text = self._extract_pdf(abs_path)
                # FR-004: Если получили хоть какой-то текст, пропускаем fallback для скорости
                if len(text.strip()) < 50:  # Только если текста совсем мало
                    # Fallback: pdfminer.six
                    try:
                        from pdfminer.high_level import extract_text  # type: ignore
                        t2 = extract_text(abs_path) or ""
                        if len(t2.strip()) > len(text.strip()):
                            text = t2
                    except Exception:
                        pass
                if not text.strip():
                    # FR-004: OCR только 2 первые страницы (было 3) для ускорения
                    ocr_text = self._ocr_pdf_pages(abs_path, max_pages=2)
                    if ocr_text:
                        text = ocr_text
                        ocr_used = True
            elif ext == "docx":
                text = self._extract_docx(abs_path)
                # OCR images inside DOCX (best effort)
                ocr_text = self._ocr_docx_images(abs_path)
                if ocr_text:
                    text = (text + "\n" + ocr_text).strip()
                    ocr_used = True
            elif ext == "doc":
                text = self._extract_doc(abs_path)
            elif ext == "xlsx":
                text = self._extract_xlsx(abs_path)
            elif ext == "xls":
                text = self._extract_xls(abs_path)
        except Exception:
            self._log.exception("Ошибка извлечения текста: %s", rel_path)
            text = ""

        text = self._normalize_text(text)
        meta = {
            "format": ext.upper(),
            "length": len(text),
            "date": datetime.fromtimestamp(os.path.getmtime(abs_path)).strftime("%Y-%m-%d %H:%M"),
            "ocr": ocr_used,
            "quality": self._estimate_quality(text),
            "source": source,
        }
        return text, meta

    def _write_entry(self, out, rel_path: str, text: str, meta: dict):
        # Дополнительная защита: не пишем запись для самого индексного файла
        if os.path.basename(rel_path) == "_search_index.txt":
            return
        out.write(f"{HEADER_BAR}\n")
        out.write(f"ЗАГОЛОВОК: {rel_path}\n")
        out.write(
            "Формат: {fmt} | Символов: {length} | Дата: {date} | OCR: {ocr} | Качество: {quality}%\n".format(
                fmt=meta.get("format", ""),
                length=meta.get("length", 0),
                date=meta.get("date", ""),
                ocr="да" if meta.get("ocr") else "нет",
                quality=meta.get("quality", 0),
            )
        )
        out.write(f"Источник: {meta.get('source','filesystem')}\n")
        out.write(f"{HEADER_BAR}\n")
        out.write(f"{DOC_START_MARKER}\n")
        out.write((text or "").strip() + "\n")
        out.write(f"{DOC_END_MARKER}\n\n")

    # ---------- Helpers ----------
    def _read_text_with_encoding(self, path: str) -> str:
        try:
            import chardet  # type: ignore
        except Exception:
            chardet = None
        encodings = ["utf-8", "cp1251", "cp866", "iso-8859-1"]
        if chardet:
            try:
                with open(path, "rb") as f:
                    raw = f.read(8192)
                det = chardet.detect(raw)
                if det and det.get("encoding"):
                    encodings = [det["encoding"]] + [e for e in encodings if e != det["encoding"]]
            except Exception:
                pass
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    return f.read()
            except Exception:
                continue
        # last resort
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _normalize_text(self, text: str) -> str:
        import unicodedata, re
        if not text:
            return ""
        t = unicodedata.normalize("NFKC", text)
        t = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", " ", t)
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    def _html_to_text(self, html: str) -> str:
        """Очень простая очистка HTML без внешних зависимостей: убираем теги, скрипты/стили, декодируем сущности."""
        if not html:
            return ""
        import re, html as h
        # Удаляем содержимое <script> и <style>
        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
        # Удаляем остальные теги
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        # Декодируем HTML-сущности
        cleaned = h.unescape(cleaned)
        return cleaned

    def _estimate_quality(self, text: str) -> int:
        if not text:
            return 0
        import re
        letters = len(re.findall(r"[A-Za-zА-Яа-яЁё]", text))
        ratio = letters / max(1, len(text))
        return int(min(100, max(0, ratio * 100)))

    def _extract_pdf(self, path: str, max_pages: int = 100) -> str:
        """FR-004: Извлечение текста из PDF с ограничением по страницам для оптимизации."""
        try:
            import pdfplumber  # type: ignore
            txt = []
            with pdfplumber.open(path) as pdf:
                # FR-004: Ограничиваем количество страниц для ускорения
                for page in pdf.pages[:max_pages]:
                    t = page.extract_text() or ""
                    if t:
                        txt.append(t)
            return "\n".join(txt).strip()
        except Exception:
            try:
                import pypdf  # type: ignore
                txt = []
                with open(path, "rb") as f:
                    r = pypdf.PdfReader(f)
                    # Попробуем расшифровать без пароля (часто помогает для "безопасных" PDF)
                    try:
                        if getattr(r, "is_encrypted", False):
                            try:
                                r.decrypt("")
                            except Exception:
                                try:
                                    r.decrypt(None)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # FR-004: Ограничиваем количество страниц
                    pages_to_process = r.pages[:max_pages] if len(r.pages) > max_pages else r.pages
                    for p in pages_to_process:
                        t = p.extract_text() or ""
                        if t:
                            txt.append(t)
                return "\n".join(txt).strip()
            except Exception:
                # PyMuPDF (fitz) как дополнительный fallback
                try:
                    import fitz  # type: ignore
                    doc = fitz.open(path)
                    parts = []
                    # FR-004: Ограничиваем количество страниц
                    for i, page in enumerate(doc):
                        if i >= max_pages:
                            break
                        t = page.get_text("text") or ""
                        if t:
                            parts.append(t)
                    return "\n".join(parts).strip()
                except Exception:
                    return ""

    def _ocr_pdf_pages(self, path: str, max_pages: int = 3) -> str:
        """Best-effort OCR: конвертирует первые N страниц в изображения и распознаёт текст.
        Требует системные зависимости (poppler для pdf2image и tesseract для OCR)."""
        if max_pages <= 0:
            return ""
        try:
            from pdf2image import convert_from_path  # type: ignore
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore  # noqa: F401
        except Exception:
            # Зависимости не установлены — спокойно пропускаем
            self._log.debug("OCR пропущен: отсутствуют зависимости pdf2image/pytesseract/Pillow")
            return ""
        try:
            images = convert_from_path(path)
        except Exception:
            # Возможно, отсутствует poppler (pdftoppm/pdftocairo)
            self._log.debug("OCR пропущен: не удалось конвертировать PDF в изображения (вероятно, нет poppler)")
            return ""
        if not images:
            return ""
        texts: List[str] = []
        for img in images[:max_pages]:
            try:
                t = pytesseract.image_to_string(img, lang="rus+eng")
                if t and t.strip():
                    texts.append(t)
            except Exception:
                continue
        return "\n".join(texts).strip()

    def _extract_docx(self, path: str) -> str:
        try:
            import docx  # type: ignore
            d = docx.Document(path)
            parts = [p.text for p in d.paragraphs if p.text]
            # tables
            for table in d.tables:
                for row in table.rows:
                    row_txt = [cell.text for cell in row.cells if cell.text]
                    if row_txt:
                        parts.append(" | ".join(row_txt))
            return "\n".join(parts).strip()
        except Exception:
            return ""

    def _ocr_docx_images(self, path: str) -> str:
        # Read images from docx as zip and OCR
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except Exception:
            return ""
        texts: List[str] = []
        try:
            with zipfile.ZipFile(path) as z:
                for zi in z.infolist():
                    if zi.filename.startswith("word/media/") and not zi.is_dir():
                        data = z.read(zi)
                        from io import BytesIO
                        try:
                            img = Image.open(BytesIO(data))
                            t = pytesseract.image_to_string(img, lang="rus+eng")
                            if t:
                                texts.append(t)
                        except Exception:
                            continue
        except Exception:
            return ""
        return "\n".join(texts).strip()

    def _extract_doc(self, path: str) -> str:
        # Best-effort: simple binary heuristic + cp1251 decode fallback
        try:
            with open(path, "rb") as f:
                data = f.read()
            # Keep printable ASCII and cp1251 range by replacing others with space
            filtered = bytearray()
            for b in data:
                if 32 <= b <= 126 or b in (9, 10, 13) or 192 <= b <= 255:
                    filtered.append(b)
                else:
                    filtered.append(32)
            try:
                return filtered.decode("cp1251")
            except Exception:
                return filtered.decode("latin-1", errors="ignore")
        except Exception:
            return ""

    def _extract_xlsx(self, path: str, max_rows: int = 1000, max_sheets: int = 10) -> str:
        """FR-004: Извлечение текста из XLSX с ограничениями для оптимизации."""
        try:
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(path, data_only=True)
            out: List[str] = []
            # FR-004: Ограничиваем количество листов
            for ws in wb.worksheets[:max_sheets]:
                out.append(f"Лист: {ws.title}")
                row_count = 0
                for row in ws.iter_rows(values_only=True):
                    # FR-004: Ограничиваем количество строк на листе
                    if row_count >= max_rows:
                        break
                    vals = [str(v) for v in row if v is not None]
                    if vals:
                        out.append(" | ".join(vals))
                        row_count += 1
            return "\n".join(out).strip()
        except Exception:
            return ""

    def _extract_xls(self, path: str, max_rows: int = 1000, max_sheets: int = 10) -> str:
        """FR-004: Извлечение текста из XLS с ограничениями для оптимизации."""
        try:
            import xlrd  # type: ignore
            book = xlrd.open_workbook(path)
            out: List[str] = []
            # FR-004: Ограничиваем количество листов
            sheets_to_process = min(book.nsheets, max_sheets)
            for si in range(sheets_to_process):
                sh = book.sheet_by_index(si)
                out.append(f"Лист: {sh.name}")
                # FR-004: Ограничиваем количество строк
                rows_to_process = min(sh.nrows, max_rows)
                for r in range(rows_to_process):
                    vals = [str(sh.cell_value(r, c)) for c in range(sh.ncols) if sh.cell_value(r, c) not in ("", None)]
                    if vals:
                        out.append(" | ".join(vals))
            return "\n".join(out).strip()
        except Exception:
            return ""
