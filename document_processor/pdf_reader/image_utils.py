"""Утилиты для предобработки изображений перед OCR (increment-013)."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Опциональные зависимости
try:
    from PIL import Image, ImageEnhance, ImageFilter  # type: ignore
    PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    PIL_AVAILABLE = False

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    CV2_AVAILABLE = True
except Exception:  # pragma: no cover
    CV2_AVAILABLE = False


def preprocess_image_for_ocr(img: 'Image.Image', use_opencv: bool = True) -> 'Image.Image':
    """Предобработка изображения для улучшения качества OCR.
    
    Применяет следующие операции:
    - Конвертация в grayscale
    - Бинаризация (адаптивная если доступен OpenCV, иначе по порогу)
    - Увеличение резкости (опционально)
    - Нормализация DPI до 300
    
    Args:
        img: Исходное изображение (PIL Image)
        use_opencv: Использовать OpenCV для адаптивной бинаризации (если доступен)
        
    Returns:
        Обработанное изображение или исходное при ошибке
    """
    if not PIL_AVAILABLE:
        logger.warning("PIL не доступен для предобработки изображений")
        return img
    
    try:
        original = img
        
        # 1. Конвертация в grayscale
        if img.mode != 'L':
            img = img.convert('L')
        
        # 2. Бинаризация
        if use_opencv and CV2_AVAILABLE:
            try:
                # Адаптивная бинаризация через OpenCV (лучше для неравномерного освещения)
                img_array = np.array(img)
                binary = cv2.adaptiveThreshold(
                    img_array,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    11,  # размер блока
                    2    # константа, вычитаемая из среднего
                )
                img = Image.fromarray(binary)
            except Exception as e:
                logger.debug("OpenCV бинаризация не удалась: %s, используем простой порог", e)
                # Fallback на простую бинаризацию
                img = img.point(lambda x: 0 if x < 128 else 255, '1')
        else:
            # Простая бинаризация по порогу
            img = img.point(lambda x: 0 if x < 128 else 255, '1')
        
        # 3. Увеличение резкости (опционально, только если PIL)
        try:
            img = img.filter(ImageFilter.SHARPEN)
        except Exception as e:
            logger.debug("Не удалось применить фильтр резкости: %s", e)
        
        # 4. Нормализация DPI (рекомендуется 300 для OCR)
        try:
            dpi = img.info.get('dpi', (72, 72))
            if dpi[0] < 200:  # Только если DPI низкий
                scale = 300 / dpi[0]
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                img.info['dpi'] = (300, 300)
        except Exception as e:
            logger.debug("Не удалось нормализовать DPI: %s", e)
        
        logger.debug("Предобработка изображения выполнена успешно")
        return img
        
    except Exception as e:  # pragma: no cover
        logger.warning("Ошибка при предобработке изображения: %s, используем исходное", e)
        return original


def enhance_image_contrast(img: 'Image.Image', factor: float = 1.5) -> 'Image.Image':
    """Увеличение контрастности изображения.
    
    Args:
        img: Исходное изображение (PIL Image)
        factor: Коэффициент контрастности (1.0 = без изменений, >1.0 = больше контраста)
        
    Returns:
        Изображение с улучшенным контрастом или исходное при ошибке
    """
    if not PIL_AVAILABLE:
        return img
    
    try:
        enhancer = ImageEnhance.Contrast(img)
        return enhancer.enhance(factor)
    except Exception as e:  # pragma: no cover
        logger.debug("Не удалось усилить контраст: %s", e)
        return img


def denoise_image(img: 'Image.Image') -> 'Image.Image':
    """Шумоподавление изображения.
    
    Args:
        img: Исходное изображение (PIL Image)
        
    Returns:
        Изображение после шумоподавления или исходное при ошибке
    """
    if not CV2_AVAILABLE:
        # Fallback на медианный фильтр PIL
        try:
            return img.filter(ImageFilter.MedianFilter(size=3))
        except Exception:
            return img
    
    try:
        # OpenCV denoise (более качественный)
        img_array = np.array(img)
        if len(img_array.shape) == 2:  # grayscale
            denoised = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
        else:  # color
            denoised = cv2.fastNlMeansDenoisingColored(img_array, None, 10, 10, 7, 21)
        return Image.fromarray(denoised)
    except Exception as e:  # pragma: no cover
        logger.debug("Не удалось применить шумоподавление: %s", e)
        return img
