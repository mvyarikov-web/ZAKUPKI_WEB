"""Модуль чтения PDF-документов (векторные и сканы)."""
import os
import time
import logging
import unicodedata
import re
from typing import Any, Dict, List, Optional

from .analyzer import PdfAnalyzer
from .exceptions import OcrNotAvailableError

# Импорты PDF-библиотек (опциональные)
try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None  # type: ignore

try:
    import pypdf  # type: ignore
except Exception:  # pragma: no cover
    pypdf = None  # type: ignore

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:  # pragma: no cover
    pdfminer_extract_text = None  # type: ignore

try:
    import fitz  # PyMuPDF  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

# OCR-зависимости (опциональные)
try:
    import pytesseract  # type: ignore
    from pdf2image import convert_from_path  # type: ignore
    from PIL import Image  # type: ignore  # noqa: F401
    OCR_AVAILABLE = True
except Exception:  # pragma: no cover
    pytesseract = None  # type: ignore
    convert_from_path = None  # type: ignore
    OCR_AVAILABLE = False


class PdfReader:
    """Читатель PDF-документов с поддержкой векторных и сканированных файлов."""
    
    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._analyzer = PdfAnalyzer()
    
    def read_pdf(
        self,
        path: str,
        ocr: str = 'auto',
        lang: str = 'rus+eng',
        budget_seconds: float = 10.0,
        max_pages_text: int = 100,
        max_pages_ocr: int = 2
    ) -> Dict[str, Any]:
        """Извлечь текст из PDF (векторный или скан).
        
        Args:
            path: Путь к PDF-файлу
            ocr: Режим OCR: 'auto' (авто), 'force' (принудительно), 'off' (выключен)
            lang: Языки для OCR (например, 'rus+eng')
            budget_seconds: Тайм-бюджет для извлечения текста
            max_pages_text: Максимум страниц для векторного извлечения
            max_pages_ocr: Максимум страниц для OCR
            
        Returns:
            PdfReadResult (dict) с полями:
                - text: извлечённый текст
                - pages: количество страниц
                - ocr_used: использовался ли OCR
                - used_extractor: имя использованного экстрактора
                - elapsed_ms: время обработки в миллисекундах
                - has_text_layer: есть ли текстовый слой
                - attempts: список попыток извлечения
        """
        start = time.time()
        self._log.info("Начало чтения PDF: %s (ocr=%s, budget=%.1fs)", path, ocr, budget_seconds)
        
        # Анализ PDF
        analysis = self._analyzer.analyze_pdf(path)
        pages = analysis.get('pages')
        
        # Определение типа PDF
        has_text = False
        if ocr != 'force':
            has_text = self.has_text_layer(path, sample_pages=2, min_text_len=50)
        
        # Извлечение текста
        text = ''
        ocr_used = False
        used_extractor = 'none'
        attempts: List[Dict[str, Any]] = []
        
        if ocr == 'force' or (ocr == 'auto' and not has_text):
            # OCR для сканов или принудительный OCR
            text, ocr_attempts = self._extract_text_ocr(
                path, max_pages=max_pages_ocr, lang=lang
            )
            if text:
                ocr_used = True
                used_extractor = 'ocr'
            attempts.extend(ocr_attempts)
        
        if not text and ocr != 'force':
            # Векторное извлечение (каскад экстракторов)
            text, used_extractor, attempts = self._extract_text_vector(
                path, budget_seconds=budget_seconds, max_pages=max_pages_text
            )
        
        # Нормализация текста
        text = self._normalize_text(text)
        
        elapsed_ms = int((time.time() - start) * 1000)
        
        result = {
            'text': text,
            'pages': pages,
            'ocr_used': ocr_used,
            'used_extractor': used_extractor,
            'elapsed_ms': elapsed_ms,
            'has_text_layer': has_text,
            'attempts': attempts,
        }
        
        self._log.info(
            "Чтение PDF завершено: %s | extractor=%s | ocr=%s | elapsed=%dms | pages=%s",
            path, used_extractor, ocr_used, elapsed_ms, pages
        )
        
        return result
    
    def has_text_layer(
        self, path: str, sample_pages: int = 2, min_text_len: int = 50
    ) -> bool:
        """Определить наличие текстового слоя в PDF.
        
        Args:
            path: Путь к PDF-файлу
            sample_pages: Количество страниц для проверки
            min_text_len: Минимальная длина текста для определения как "векторный"
            
        Returns:
            True если PDF векторный (есть текстовый слой), False если скан
        """
        try:
            if pdfplumber is not None:
                with pdfplumber.open(path) as pdf:
                    text_len = 0
                    for i, page in enumerate(pdf.pages[:sample_pages]):
                        t = page.extract_text() or ''
                        text_len += len(t.strip())
                        if text_len >= min_text_len:
                            return True
                    return False
            elif pypdf is not None:
                with open(path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    text_len = 0
                    pages_to_check = reader.pages[:sample_pages]
                    for p in pages_to_check:
                        t = p.extract_text() or ''
                        text_len += len(t.strip())
                        if text_len >= min_text_len:
                            return True
                    return False
            else:
                # Нет доступных экстракторов — предполагаем векторный
                return True
        except Exception as e:
            self._log.debug("Ошибка при определении типа PDF: %s", e)
            return False
    
    def _extract_text_vector(
        self, path: str, budget_seconds: float, max_pages: int
    ) -> tuple[str, str, List[Dict[str, Any]]]:
        """Извлечение текста из векторного PDF через каскад экстракторов.
        
        Args:
            path: Путь к PDF-файлу
            budget_seconds: Тайм-бюджет
            max_pages: Максимум страниц
            
        Returns:
            Кортеж: (text, used_extractor, attempts)
        """
        start = time.time()
        attempts: List[Dict[str, Any]] = []
        text = ''
        used = 'none'
        
        def left_time() -> float:
            return budget_seconds - (time.time() - start)
        
        # 1) pdfplumber
        if text == '' and left_time() > 0 and pdfplumber is not None:
            t0 = time.time()
            ok, err = False, None
            try:
                with pdfplumber.open(path) as pdf:
                    parts = []
                    for i, page in enumerate(pdf.pages):
                        if i >= max_pages or left_time() <= 0:
                            break
                        t = page.extract_text() or ''
                        if t:
                            parts.append(t)
                if parts:
                    text = '\n'.join(parts)
                    used = 'pdfplumber'
                    ok = True
            except Exception as e:  # pragma: no cover
                err = f'{type(e).__name__}: {e}'
                self._log.debug("pdfplumber не удалось: %s", err)
            attempts.append({
                'name': 'pdfplumber',
                'ok': ok,
                'elapsed_ms': int((time.time() - t0) * 1000),
                'error': err
            })
        
        # 2) pypdf
        if text == '' and left_time() > 0 and pypdf is not None:
            t0 = time.time()
            ok, err = False, None
            try:
                with open(path, 'rb') as f:
                    r = pypdf.PdfReader(f)
                    try:
                        if getattr(r, 'is_encrypted', False):
                            try:
                                r.decrypt("")
                            except Exception:
                                try:
                                    r.decrypt(None)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    parts = []
                    for i, p in enumerate(r.pages):
                        if i >= max_pages or left_time() <= 0:
                            break
                        t = p.extract_text() or ''
                        if t:
                            parts.append(t)
                if parts:
                    text = '\n'.join(parts)
                    used = 'pypdf'
                    ok = True
            except Exception as e:  # pragma: no cover
                err = f'{type(e).__name__}: {e}'
                self._log.debug("pypdf не удалось: %s", err)
            attempts.append({
                'name': 'pypdf',
                'ok': ok,
                'elapsed_ms': int((time.time() - t0) * 1000),
                'error': err
            })
        
        # 3) pdfminer.six
        if text == '' and left_time() > 0 and pdfminer_extract_text is not None:
            t0 = time.time()
            ok, err = False, None
            try:
                t = pdfminer_extract_text(path) or ''
                if t.strip():
                    text = t
                    used = 'pdfminer'
                    ok = True
            except Exception as e:  # pragma: no cover
                err = f'{type(e).__name__}: {e}'
                self._log.debug("pdfminer не удалось: %s", err)
            attempts.append({
                'name': 'pdfminer',
                'ok': ok,
                'elapsed_ms': int((time.time() - t0) * 1000),
                'error': err
            })
        
        # 4) PyMuPDF
        if text == '' and left_time() > 0 and fitz is not None:
            t0 = time.time()
            ok, err = False, None
            try:
                doc = fitz.open(path)
                parts = []
                for i, page in enumerate(doc):
                    if i >= max_pages or left_time() <= 0:
                        break
                    t = page.get_text("text") or ''
                    if t:
                        parts.append(t)
                if parts:
                    text = '\n'.join(parts)
                    used = 'pymupdf'
                    ok = True
            except Exception as e:  # pragma: no cover
                err = f'{type(e).__name__}: {e}'
                self._log.debug("pymupdf не удалось: %s", err)
            attempts.append({
                'name': 'pymupdf',
                'ok': ok,
                'elapsed_ms': int((time.time() - t0) * 1000),
                'error': err
            })
        
        return text, used, attempts
    
    def _extract_text_ocr(
        self, path: str, max_pages: int, lang: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Извлечение текста через OCR.
        
        Args:
            path: Путь к PDF-файлу
            max_pages: Максимум страниц для OCR
            lang: Языки для распознавания
            
        Returns:
            Кортеж: (text, attempts)
        """
        attempts: List[Dict[str, Any]] = []
        
        if not OCR_AVAILABLE:
            self._log.warning(
                "OCR пропущен: отсутствуют зависимости (pytesseract/pdf2image/Pillow)"
            )
            attempts.append({
                'name': 'ocr',
                'ok': False,
                'elapsed_ms': 0,
                'error': 'OCR dependencies not available'
            })
            return '', attempts
        
        t0 = time.time()
        ok, err = False, None
        text = ''
        
        try:
            images = convert_from_path(path)
            if images:
                texts: List[str] = []
                for i, img in enumerate(images[:max_pages]):
                    try:
                        t = pytesseract.image_to_string(img, lang=lang)
                        if t and t.strip():
                            texts.append(t)
                    except Exception as e:
                        self._log.debug("OCR страницы %d не удалось: %s", i + 1, e)
                        continue
                if texts:
                    text = '\n'.join(texts)
                    ok = True
        except Exception as e:  # pragma: no cover
            err = f'{type(e).__name__}: {e}'
            self._log.warning("OCR не удалось: %s", err)
        
        attempts.append({
            'name': 'ocr',
            'ok': ok,
            'elapsed_ms': int((time.time() - t0) * 1000),
            'error': err
        })
        
        return text, attempts
    
    def _normalize_text(self, text: str) -> str:
        """Нормализация извлечённого текста.
        
        Args:
            text: Исходный текст
            
        Returns:
            Нормализованный текст
        """
        if not text:
            return ""
        
        # Унификация Unicode
        t = unicodedata.normalize('NFKC', text)
        
        # Удаление невидимых символов
        t = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', ' ', t)
        
        # Схлопывание пробелов
        t = re.sub(r'\s+', ' ', t)
        
        # Trim
        return t.strip()
