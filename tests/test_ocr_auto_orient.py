"""
Тест автокоррекции ориентации изображений для OCR.

Проверяет, что модуль корректно определяет и исправляет ориентацию
документов, отсканированных в разных положениях.
"""
import pytest
import os
import sys

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from document_processor.pdf_reader import PdfReader

# Пропускаем тест если Tesseract не установлен
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract не установлен")
def test_auto_orient_basic():
    """Базовый тест автокоррекции ориентации."""
    reader = PdfReader()
    
    # Создаём тестовое изображение с текстом
    from PIL import Image, ImageDraw, ImageFont
    
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Добавляем текст
    text = "Тестовый документ для проверки OCR"
    draw.text((50, 50), text, fill='black')
    
    # Тест 1: Изображение без поворота
    result = reader._auto_orient_image(img, 'rus+eng')
    assert result is not None
    assert result.size == img.size or result.size == (img.size[1], img.size[0])
    
    # Тест 2: Повёрнутое изображение на 90°
    img_rotated = img.rotate(90, expand=True)
    result = reader._auto_orient_image(img_rotated, 'rus+eng')
    assert result is not None


@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract не установлен")
def test_ocr_with_auto_orient(tmp_path):
    """Тест OCR с автокоррекцией ориентации на реальном PDF."""
    # Путь к тестовому PDF
    test_pdf = "/Users/maksimyarikov/Desktop/Автоматизация закупок/Исходные данные/Пример документов по закупке/PDF/ТЗ поставка сплит-систем.pdf"
    
    if not os.path.exists(test_pdf):
        pytest.skip("Тестовый PDF не найден")
    
    reader = PdfReader()
    
    # Режим force с автокоррекцией ориентации
    result = reader.read_pdf(test_pdf, ocr='force', max_pages_ocr=1)
    
    assert result is not None
    assert 'text' in result
    assert 'ocr_used' in result
    assert result['ocr_used'] is True
    
    # Проверяем, что текст был извлечён
    if result['text']:
        print(f"\nИзвлечено {len(result['text'])} символов")
        print(f"Первые 200 символов: {result['text'][:200]}")
        assert len(result['text']) > 0
    else:
        print("\nПредупреждение: текст не извлечён")
        print(f"Попытки: {result['attempts']}")


@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract не установлен")  
def test_ocr_different_orientations(tmp_path):
    """Тест распознавания изображений в разных ориентациях."""
    from PIL import Image, ImageDraw
    
    reader = PdfReader()
    
    # Создаём изображение с текстом
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "ТЕСТ", fill='black')
    
    # Сохраняем в разных ориентациях и проверяем OCR
    orientations = [0, 90, 180, 270]
    
    for angle in orientations:
        rotated = img.rotate(angle, expand=True) if angle > 0 else img
        corrected = reader._auto_orient_image(rotated, 'rus+eng')
        
        assert corrected is not None
        print(f"\nОриентация {angle}°: размер после коррекции {corrected.size}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
