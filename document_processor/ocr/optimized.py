"""Оптимизированный модуль OCR с предобработкой и кэшем ориентации."""
import logging
from typing import Any, Optional, Dict
from pathlib import Path

# OCR зависимости (опциональные)
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    OCR_AVAILABLE = True
except Exception:
    pytesseract = None
    Image = None
    OCR_AVAILABLE = False

# OpenCV для предобработки (опциональное)
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    np = None
    CV2_AVAILABLE = False


class DocumentOrientationCache:
    """Кэш ориентации документов для ускорения OCR."""
    
    def __init__(self):
        self._cache: Dict[str, int] = {}
        self._log = logging.getLogger(__name__)
    
    def get_orientation(self, pdf_path: str, page_num: int = 0) -> Optional[int]:
        """
        Получает ориентацию для страницы документа.
        
        Если первая страница уже определена, используется для всех остальных.
        """
        cache_key = f"{pdf_path}:0"  # Используем первую страницу как эталон
        return self._cache.get(cache_key)
    
    def set_orientation(self, pdf_path: str, page_num: int, angle: int):
        """Сохраняет ориентацию для документа."""
        if page_num == 0:  # Кэшируем только первую страницу
            cache_key = f"{pdf_path}:0"
            self._cache[cache_key] = angle
            self._log.debug(f"Кэшируем ориентацию {angle}° для {Path(pdf_path).name}")
    
    def clear(self):
        """Очищает кэш."""
        self._cache.clear()


class OptimizedOcrProcessor:
    """Оптимизированный OCR с OSD, предобработкой и кэшем ориентации."""
    
    # Оптимизированная конфигурация Tesseract для рус+англ документов
    OCR_CONFIG = (
        '--psm 6 '  # Uniform text block (для документов)
        '-c tessedit_char_whitelist='
        'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        '0123456789.,!?;:()[]{}/"№%@#$&*+-= \t\n'
    )
    
    def __init__(
        self,
        use_osd: bool = True,
        use_preprocessing: bool = True,
        cache_orientation: bool = True,
        target_dpi: int = 300
    ):
        """
        Args:
            use_osd: Использовать OSD для определения ориентации
            use_preprocessing: Применять предобработку изображений
            cache_orientation: Кэшировать ориентацию документов
            target_dpi: Целевой DPI для изображений
        """
        self.use_osd = use_osd and OCR_AVAILABLE
        self.use_preprocessing = use_preprocessing and CV2_AVAILABLE
        self.cache_orientation = cache_orientation
        self.target_dpi = target_dpi
        
        self._orientation_cache = DocumentOrientationCache() if cache_orientation else None
        self._log = logging.getLogger(__name__)
    
    def detect_orientation_osd(self, img: Any) -> int:
        """
        Определяет ориентацию изображения с помощью Tesseract OSD.
        
        Это гораздо быстрее, чем 4x полный OCR (в 3-4 раза).
        
        Returns:
            Угол поворота (0, 90, 180, 270)
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return 0
        
        try:
            # OSD (Orientation and Script Detection) — быстрый анализ ориентации
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            rotation = osd.get('rotate', 0)
            
            # Tesseract возвращает угол, на который нужно повернуть ПРОТИВ часовой
            # Нормализуем к стандартным углам
            rotation = int(rotation) % 360
            
            self._log.debug(f"OSD определил ориентацию: {rotation}°, уверенность: {osd.get('orientation_conf', 0):.1f}")
            return rotation
            
        except Exception as e:
            self._log.debug(f"OSD не удалось: {e}, используем fallback")
            return self._detect_orientation_fallback(img)
    
    def _detect_orientation_fallback(self, img: Any) -> int:
        """
        Упрощённая эвристика определения ориентации без OSD.
        
        Быстрая проверка только 0° и 90° (самые распространённые).
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return 0
        
        try:
            # Проверяем только 0° и 90° (99% документов)
            width, height = img.size
            box = (width // 4, height // 4, 3 * width // 4, 3 * height // 4)
            
            # 0°
            text_0 = pytesseract.image_to_string(
                img.crop(box), 
                lang='rus+eng', 
                config='--psm 6'
            ).strip()
            
            # 90°
            rotated_90 = img.rotate(90, expand=True)
            w90, h90 = rotated_90.size
            box_90 = (w90 // 4, h90 // 4, 3 * w90 // 4, 3 * h90 // 4)
            text_90 = pytesseract.image_to_string(
                rotated_90.crop(box_90),
                lang='rus+eng',
                config='--psm 6'
            ).strip()
            
            # Выбираем ориентацию с большим количеством текста
            if len(text_90) > len(text_0) * 1.2:  # 20% перевес
                return 90
            return 0
            
        except Exception as e:
            self._log.debug(f"Fallback ориентации не удался: {e}")
            return 0
    
    def preprocess_image(self, img: Any) -> Any:
        """
        Предобработка изображения для улучшения качества OCR.
        
        - Конверсия в grayscale
        - Бинаризация (Otsu thresholding)
        - Шумоподавление (median filter)
        - DPI нормализация
        
        Returns:
            Предобработанное PIL Image
        """
        if not self.use_preprocessing or not CV2_AVAILABLE:
            return img
        
        try:
            # Конвертируем PIL → numpy array
            img_array = np.array(img)
            
            # Grayscale (если цветное)
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Otsu binarization (автоматический порог)
            _, binary = cv2.threshold(
                gray, 
                0, 
                255, 
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            
            # Median filter для шумоподавления (kernel 3x3)
            denoised = cv2.medianBlur(binary, 3)
            
            # Конвертируем обратно в PIL Image
            preprocessed = Image.fromarray(denoised) if Image else img
            
            self._log.debug("Предобработка изображения выполнена")
            return preprocessed
            
        except Exception as e:
            self._log.debug(f"Предобработка не удалась: {e}, используем оригинал")
            return img
    
    def extract_text_optimized(
        self,
        img: Any,
        lang: str = 'rus+eng',
        pdf_path: Optional[str] = None,
        page_num: int = 0
    ) -> str:
        """
        Оптимизированное извлечение текста с OCR.
        
        Args:
            img: PIL Image объект
            lang: Языки для OCR
            pdf_path: Путь к PDF (для кэширования ориентации)
            page_num: Номер страницы
            
        Returns:
            Распознанный текст
        """
        if not OCR_AVAILABLE or pytesseract is None:
            return ""
        
        try:
            # 1. Определяем ориентацию
            rotation = 0
            
            if pdf_path and self._orientation_cache and page_num > 0:
                # Для страниц после первой используем кэш
                cached = self._orientation_cache.get_orientation(pdf_path, page_num)
                if cached is not None:
                    rotation = cached
                    self._log.debug(f"Используем кэшированную ориентацию: {rotation}°")
            else:
                # Для первой страницы определяем ориентацию
                if self.use_osd:
                    rotation = self.detect_orientation_osd(img)
                else:
                    rotation = self._detect_orientation_fallback(img)
                
                # Кэшируем для следующих страниц
                if pdf_path and self._orientation_cache and page_num == 0:
                    self._orientation_cache.set_orientation(pdf_path, page_num, rotation)
            
            # 2. Поворачиваем изображение
            if rotation != 0:
                img = img.rotate(rotation, expand=True)
            
            # 3. Предобработка
            if self.use_preprocessing:
                img = self.preprocess_image(img)
            
            # 4. OCR с оптимизированной конфигурацией
            text = pytesseract.image_to_string(
                img,
                lang=lang,
                config=self.OCR_CONFIG
            )
            
            return text.strip()
            
        except Exception as e:
            self._log.exception(f"Ошибка OCR: {e}")
            return ""
    
    def clear_cache(self):
        """Очищает кэш ориентации."""
        if self._orientation_cache:
            self._orientation_cache.clear()
