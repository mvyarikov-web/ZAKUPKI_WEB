"""Минимальные тесты для оптимизированного OCR."""
import pytest
from document_processor.ocr.optimized import (
    OptimizedOcrProcessor, 
    DocumentOrientationCache,
    OCR_AVAILABLE,
    CV2_AVAILABLE
)


def test_orientation_cache_creation():
    """Создание кэша ориентации."""
    cache = DocumentOrientationCache()
    assert cache is not None


def test_orientation_cache_operations():
    """Операции с кэшем ориентации."""
    cache = DocumentOrientationCache()
    
    # Пустой кэш
    assert cache.get_orientation("test.pdf", 0) is None
    
    # Добавление ориентации
    cache.set_orientation("test.pdf", 0, 90)
    assert cache.get_orientation("test.pdf", 0) == 90
    
    # Очистка
    cache.clear()
    assert cache.get_orientation("test.pdf", 0) is None


def test_ocr_processor_creation():
    """Создание оптимизированного OCR процессора."""
    processor = OptimizedOcrProcessor()
    assert processor is not None
    assert processor.target_dpi == 300


def test_ocr_processor_configuration():
    """Конфигурация OCR процессора."""
    processor = OptimizedOcrProcessor(
        use_osd=False,
        use_preprocessing=False,
        cache_orientation=False,
        target_dpi=150
    )
    
    assert processor.use_osd is False
    assert processor.cache_orientation is False
    assert processor.target_dpi == 150


@pytest.mark.skipif(not OCR_AVAILABLE, reason="Tesseract недоступен")
def test_detect_orientation_fallback():
    """Fallback определение ориентации работает без OSD."""
    try:
        from PIL import Image
        import numpy as np
        
        # Создаём простое тестовое изображение
        img_array = np.ones((100, 200, 3), dtype=np.uint8) * 255
        img = Image.fromarray(img_array)
        
        processor = OptimizedOcrProcessor(use_osd=False)
        rotation = processor._detect_orientation_fallback(img)
        
        # Должен вернуть какой-то угол (обычно 0)
        assert rotation in [0, 90, 180, 270]
        
    except ImportError:
        pytest.skip("PIL недоступен")


def test_clear_cache():
    """Очистка кэша процессора."""
    processor = OptimizedOcrProcessor(cache_orientation=True)
    processor.clear_cache()
    # Не должно вызвать исключений


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--timeout=10'])
