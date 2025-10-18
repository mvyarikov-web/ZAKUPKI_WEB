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

# Предобработка изображений для OCR (опционально)
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    OPENCV_AVAILABLE = True
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    OPENCV_AVAILABLE = False


class PdfReader:
    """Читатель PDF-документов с поддержкой векторных и сканированных файлов."""
    
    def __init__(
        self,
        use_osd: bool = True,
        cache_orientation: bool = True,
        preprocess_images: bool = True,
        target_dpi: int = 300,
        psm_mode: int = 6
    ):
        self._log = logging.getLogger(__name__)
        self._analyzer = PdfAnalyzer()
        
        # Конфигурация оптимизаций OCR (Инкремент 13)
        self._use_osd = use_osd
        self._cache_orientation = cache_orientation
        self._preprocess_images = preprocess_images
        self._target_dpi = target_dpi
        self._psm_mode = psm_mode
        
        # Кэш ориентации документов (путь -> угол)
        self._orientation_cache: Dict[str, int] = {}
    
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
        """Извлечение текста через OCR (оптимизированная версия).
        
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
                
                # Сброс кэша ориентации для нового документа
                if self._cache_orientation:
                    self._orientation_cache[path] = None  # type: ignore[assignment]
                
                for i, img in enumerate(images[:max_pages]):
                    try:
                        # Предобработка изображения
                        img_preprocessed = self._preprocess_image(img)
                        
                        # Автокоррекция ориентации (с кэшем для документа)
                        if self._cache_orientation and path in self._orientation_cache:
                            cached_angle = self._orientation_cache[path]
                            if cached_angle is not None and cached_angle != 0:
                                # Используем закэшированную ориентацию
                                img_corrected = img_preprocessed.rotate(cached_angle, expand=True)
                                self._log.debug("Страница %d: использую кэш ориентации %d°", i + 1, cached_angle)
                            else:
                                img_corrected = img_preprocessed
                        else:
                            # Определяем ориентацию для первой страницы
                            img_corrected = self._auto_orient_image(img_preprocessed, lang)
                            
                            # Кэшируем ориентацию для остальных страниц документа
                            if self._cache_orientation and i == 0:
                                # Вычисляем угол поворота из img_corrected
                                # (сравниваем размеры до/после)
                                if img_preprocessed.size != img_corrected.size:
                                    # Повёрнуто - сохраняем 90°
                                    self._orientation_cache[path] = 90
                                    self._log.debug("Кэширую ориентацию 90° для документа")
                                else:
                                    self._orientation_cache[path] = 0
                        
                        # OCR с оптимизированными настройками
                        config = f'--psm {self._psm_mode}'
                        t = pytesseract.image_to_string(img_corrected, lang=lang, config=config)
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
    
    def _preprocess_image(self, img: Any) -> Any:
        """Предобработка изображения для улучшения качества OCR.
        
        Применяет:
        - Конверсию в grayscale
        - Бинаризацию (Otsu thresholding)
        - Удаление шума (median filter)
        - Нормализацию DPI
        
        Args:
            img: PIL Image объект
            
        Returns:
            Обработанный PIL Image или оригинал при ошибке
        """
        if not OPENCV_AVAILABLE or not self._preprocess_images:
            return img
        
        try:
            # Конвертируем PIL Image в numpy array
            img_array = np.array(img)
            
            # Конверсия в grayscale если цветное
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Otsu binarization для улучшения контраста
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Median filter для удаления шума (kernel size 3x3)
            denoised = cv2.medianBlur(binary, 3)
            
            # Конвертируем обратно в PIL Image
            from PIL import Image as PILImage
            preprocessed = PILImage.fromarray(denoised)
            
            self._log.debug("Предобработка изображения успешна (grayscale + Otsu + denoise)")
            return preprocessed
            
        except Exception as e:
            self._log.debug("Предобработка изображения не удалась: %s, используем оригинал", e)
            return img
    
    def _auto_orient_image(self, img: Any, lang: str) -> Any:
        """Автоматическая коррекция ориентации изображения для OCR (оптимизированная).
        
        Использует OSD (Orientation and Script Detection) Tesseract для быстрого
        определения ориентации вместо 4x полного OCR. Fallback на эвристику при недоступности OSD.
        
        Args:
            img: PIL Image объект
            lang: Языки для OCR
            
        Returns:
            PIL Image с оптимальной ориентацией
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return img
        
        try:
            # Попытка использовать OSD для быстрого определения ориентации
            if self._use_osd:
                angle = self._detect_orientation_osd(img)
                if angle is not None:
                    if angle == 0:
                        self._log.debug("OSD: ориентация корректна (0°)")
                        return img
                    else:
                        self._log.info("OSD: поворот изображения на %d°", angle)
                        return img.rotate(angle, expand=True)
            
            # Fallback: упрощённая эвристика (1 пробный OCR вместо 4)
            return self._detect_orientation_fallback(img, lang)
                
        except Exception as e:
            self._log.debug("Автокоррекция ориентации не удалась: %s, используем оригинал", e)
            return img
    
    def _detect_orientation_osd(self, img: Any) -> Optional[int]:
        """Определение ориентации через Tesseract OSD.
        
        Args:
            img: PIL Image объект
            
        Returns:
            Угол поворота (0, 90, 180, 270) или None при ошибке
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return None
        
        try:
            # Используем OSD для определения ориентации
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            rotate = osd.get('rotate', 0)
            confidence = osd.get('orientation_conf', 0)
            
            self._log.debug("OSD результат: rotate=%d°, confidence=%.1f", rotate, confidence)
            
            # Принимаем результат при достаточной уверенности
            if confidence > 1.0:  # минимальный порог уверенности
                return rotate
            
            return None
            
        except Exception as e:
            self._log.debug("OSD не удалось: %s", e)
            return None
    
    def _detect_orientation_fallback(self, img: Any, lang: str) -> Any:
        """Упрощённая эвристика определения ориентации (fallback).
        
        Пробует только 0° и 90° (самые частые случаи) вместо всех 4 ориентаций.
        
        Args:
            img: PIL Image объект
            lang: Языки для OCR
            
        Returns:
            PIL Image с лучшей ориентацией
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return img
        
        try:
            # Пробуем только 2 самые частые ориентации: 0° и 90°
            rotations = [0, 90]
            best_rotation = 0
            best_score = -1
            
            for angle in rotations:
                try:
                    # Поворачиваем изображение
                    if angle == 0:
                        rotated = img
                    else:
                        rotated = img.rotate(angle, expand=True)
                    
                    # Пробуем распознать текст (с сокращённой областью для скорости)
                    width, height = rotated.size
                    # Берём центральную область (50% от размера) для быстрого теста
                    box = (width // 4, height // 4, 3 * width // 4, 3 * height // 4)
                    cropped = rotated.crop(box)
                    
                    # Распознаём текст с оптимизированными настройками
                    config = f'--psm {self._psm_mode}'
                    text = pytesseract.image_to_string(cropped, lang=lang, config=config)
                    text_clean = text.strip()
                    
                    # Вычисляем оценку качества
                    total_chars = len(text_clean)
                    if total_chars == 0:
                        score = 0
                    else:
                        # Считаем кириллические и латинские символы
                        cyrillic_latin = sum(1 for c in text_clean if ('\u0400' <= c <= '\u04FF' or 
                                                                         'a' <= c.lower() <= 'z'))
                        # Считаем цифры
                        digits = sum(1 for c in text_clean if c.isdigit())
                        # Считаем пробелы
                        spaces = sum(1 for c in text_clean if c == ' ')
                        
                        # Доля полезных символов
                        useful = cyrillic_latin + digits + spaces
                        useful_ratio = useful / total_chars if total_chars > 0 else 0
                        
                        # Доля букв
                        letter_ratio = cyrillic_latin / total_chars if total_chars > 0 else 0
                        
                        # Итоговая оценка
                        score = total_chars * useful_ratio * letter_ratio
                    
                    self._log.debug(
                        "Fallback ориентация %d°: символов=%d, оценка=%.1f",
                        angle, total_chars, score
                    )
                    
                    # Выбираем ориентацию с лучшей оценкой
                    if score > best_score:
                        best_score = score
                        best_rotation = angle
                        
                except Exception as e:
                    self._log.debug("Ошибка при проверке ориентации %d°: %s", angle, e)
                    continue
            
            # Возвращаем изображение с лучшей ориентацией
            if best_rotation == 0:
                self._log.debug("Fallback: поворот не требуется")
                return img
            else:
                self._log.info("Fallback: изображение повёрнуто на %d° (оценка: %.1f)", best_rotation, best_score)
                return img.rotate(best_rotation, expand=True)
                
        except Exception as e:
            self._log.debug("Fallback ориентация не удалась: %s, используем оригинал", e)
            return img
    
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
