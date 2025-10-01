from __future__ import annotations
import io
import os
import re
import logging
from typing import List, Dict, Any

HEADER_BAR_RE = re.compile(r"^=+\s*$")
HEADER_PREFIXES = (
    "ЗАГОЛОВОК:",
    "Формат:",
    "Источник:",
)

class Searcher:
    def search(self, index_path: str, keywords: List[str], *, context: int = 80, exclude_mode: bool = False) -> List[Dict]:
        if not os.path.isfile(index_path):
            raise FileNotFoundError(index_path)
        log = logging.getLogger(__name__)
        log.info("Поиск по индексу: %s, terms=%s, context=%d, exclude_mode=%s", index_path, keywords, context, exclude_mode)
        text = self._read_index(index_path)
        entries = self._parse_entries(text)
        results: List[Dict[str, Any]] = []
        
        if exclude_mode:
            # Режим исключения: возвращаем файлы, которые НЕ содержат ни одного из ключевых слов
            for entry in entries:
                body = entry.get("body", "")
                contains_keyword = False
                
                for kw in [k.strip() for k in keywords if k and k.strip()]:
                    if not kw:
                        continue
                    # Проверяем прямое совпадение
                    if re.search(re.escape(kw), body, flags=re.IGNORECASE):
                        contains_keyword = True
                        break
                    # Проверяем толерантное совпадение для коротких терминов
                    if 2 <= len(kw) <= 8:
                        gap_class = r"[\s\u00A0\u00AD\u200B\uFEFF\-]*"
                        parts = [re.escape(ch) for ch in kw]
                        pattern = re.compile("".join([parts[0]] + [gap_class + p for p in parts[1:]]), re.IGNORECASE)
                        if pattern.search(body):
                            contains_keyword = True
                            break
                
                # Если файл НЕ содержит ни одного ключевого слова - добавляем его в результаты
                if not contains_keyword:
                    # Берём первые context символов от начала документа в качестве сниппета
                    snippet = body[:context] if len(body) > 0 else ""
                    results.append({
                        "keyword": "",  # В режиме исключения нет конкретного ключевого слова
                        "position": 0,
                        "snippet": snippet,
                        "title": entry.get("title"),
                        "source": entry.get("source"),
                        "format": entry.get("format"),
                        "exclude_mode": True
                    })
        else:
            # Обычный режим: ищем файлы, которые СОДЕРЖАТ ключевые слова
            # Разделители, которые иногда встречаются внутри слов при извлечении из PDF
            # \u00A0 (NBSP), \u00AD (soft hyphen), \u200B (zero-width space), \uFEFF (BOM/ZWNBSP)
            gap_class = r"[\s\u00A0\u00AD\u200B\uFEFF\-]*"
            for entry in entries:
                body = entry.get("body", "")
                for kw in [k.strip() for k in keywords if k and k.strip()]:
                    if not kw:
                        continue
                    # 1) Прямое подстрочное совпадение
                    for m in re.finditer(re.escape(kw), body, flags=re.IGNORECASE):
                        start = max(0, m.start() - context)
                        end = min(len(body), m.end() + context)
                        snippet = body[start:end]
                        results.append({
                            "keyword": kw,
                            "position": m.start(),
                            "snippet": snippet,
                            "title": entry.get("title"),
                            "source": entry.get("source"),
                            "format": entry.get("format"),
                        })
                    # 2) Толерантное совпадение: допускаем разделители между буквами (актуально для PDF)
                    # Применяем только для коротких терминов (2..8), чтобы не раздувать шум
                    if 2 <= len(kw) <= 8:
                        # Построим шаблон вида: з[gap]а[gap]х[gap]...
                        parts = [re.escape(ch) for ch in kw]
                        pattern = re.compile("".join([parts[0]] + [gap_class + p for p in parts[1:]]), re.IGNORECASE)
                        for m in pattern.finditer(body):
                            start = max(0, m.start() - context)
                            end = min(len(body), m.end() + context)
                            snippet = body[start:end]
                            results.append({
                                "keyword": kw,
                                "position": m.start(),
                                "snippet": snippet,
                                "title": entry.get("title"),
                                "source": entry.get("source"),
                                "format": entry.get("format"),
                            })
        # naive ranking: order by keyword then position
        results.sort(key=lambda r: (r.get("title") or "", r.get("keyword", "").lower(), r["position"]))
        log.info("Поиск завершён: найдено %d совпадений", len(results))
        return results

    def _read_index(self, path: str) -> str:
        with io.open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _strip_headers(self, text: str) -> List[str]:
        lines = text.splitlines()
        out: List[str] = []
        i = 0
        n = len(lines)
        while i < n:
            ln = lines[i]
            if HEADER_BAR_RE.match(ln):
                # Expect a header block of fixed structure:
                # bar, title, meta, source, bar
                i += 1  # move to title
                # skip title/meta/source lines if present
                for _ in range(3):
                    if i < n:
                        i += 1
                # skip the closing bar if present
                if i < n and HEADER_BAR_RE.match(lines[i]):
                    i += 1
                # Now consume body until a blank line (separator) or next bar
                body: List[str] = []
                while i < n and not HEADER_BAR_RE.match(lines[i]):
                    body.append(lines[i])
                    i += 1
                # Trim trailing empty lines from body
                while body and not body[-1].strip():
                    body.pop()
                if body:
                    out.extend(body)
                # do not increment i here; next loop will process next bar or EOF
                continue
            else:
                # Lines outside any header block (unlikely) are considered content
                if not ln.startswith(HEADER_PREFIXES):
                    out.append(ln)
                i += 1
        return out

    def _parse_entries(self, text: str) -> List[Dict[str, Any]]:
        """Разбирает индекс на записи с заголовком, метаданными и телом.
        Возвращает список словарей: {title, source, format, body}.
        """
        lines = text.splitlines()
        i = 0
        n = len(lines)
        entries: List[Dict[str, Any]] = []
        while i < n:
            if not HEADER_BAR_RE.match(lines[i]):
                i += 1
                continue
            # header start
            i += 1
            title = ""
            fmt = ""
            source = ""
            if i < n and lines[i].startswith("ЗАГОЛОВОК:"):
                title = lines[i].split(":", 1)[1].strip()
                i += 1
            if i < n and lines[i].startswith("Формат:"):
                # Формат: XXX | Символов: N | Дата: ... | OCR: ... | Качество: ...
                meta_line = lines[i]
                # извлечём первое поле после "Формат: " до разделителя |
                m = re.match(r"Формат:\s*([^|]+)", meta_line)
                if m:
                    fmt = m.group(1).strip()
                i += 1
            if i < n and lines[i].startswith("Источник:"):
                source = lines[i].split(":", 1)[1].strip()
                i += 1
            # closing bar
            if i < n and HEADER_BAR_RE.match(lines[i]):
                i += 1
            # body until blank line or next bar
            body_lines: List[str] = []
            while i < n and not HEADER_BAR_RE.match(lines[i]):
                body_lines.append(lines[i])
                i += 1
            # trim trailing blanks
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            entries.append({
                "title": title,
                "format": fmt,
                "source": source or title,
                "body": "\n".join(body_lines)
            })
        return entries
