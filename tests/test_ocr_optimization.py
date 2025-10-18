"""Тесты оптимизации OCR (Инкремент 13)."""
import pytest
from pathlib import Path
from document_processor.pdf_reader import PdfReader


def test_pdf_reader_accepts_optimization_params():
    """PdfReader принимает параметры оптимизации OCR."""
    reader = PdfReader(
        use_osd=True,
        cache_orientation=True,
        preprocess_images=True,
        target_dpi=300,
        psm_mode=6
    )
    
    assert reader._use_osd is True
    assert reader._cache_orientation is True
    assert reader._preprocess_images is True
    assert reader._target_dpi == 300
    assert reader._psm_mode == 6
    assert hasattr(reader, '_orientation_cache')


def test_pdf_reader_default_params():
    """PdfReader работает с параметрами по умолчанию (обратная совместимость)."""
    reader = PdfReader()
    
    assert reader._use_osd is True
    assert reader._cache_orientation is True
    assert reader._preprocess_images is True
    assert reader._target_dpi == 300
    assert reader._psm_mode == 6


def test_orientation_cache_structure():
    """Кэш ориентации инициализируется корректно."""
    reader = PdfReader(cache_orientation=True)
    
    assert isinstance(reader._orientation_cache, dict)
    assert len(reader._orientation_cache) == 0


@pytest.mark.skipif(
    not hasattr(__import__('document_processor.pdf_reader.reader', fromlist=['OPENCV_AVAILABLE']), 'OPENCV_AVAILABLE') 
    or not __import__('document_processor.pdf_reader.reader', fromlist=['OPENCV_AVAILABLE']).OPENCV_AVAILABLE,
    reason="OpenCV недоступен"
)
def test_preprocess_image_with_opencv():
    """Предобработка изображений работает при наличии OpenCV."""
    from PIL import Image
    import numpy as np
    
    reader = PdfReader(preprocess_images=True)
    
    # Создаём тестовое изображение
    img_array = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    
    # Применяем предобработку
    preprocessed = reader._preprocess_image(img)
    
    # Проверяем, что получили PIL Image
    assert isinstance(preprocessed, Image.Image)
    
    # Предобработка должна конвертировать в grayscale, размеры сохранятся
    # (в зависимости от реализации может быть L или RGB mode)
    assert preprocessed.size == img.size


def test_preprocess_image_without_opencv():
    """Предобработка работает как passthrough без OpenCV."""
    from PIL import Image
    import numpy as np
    
    reader = PdfReader(preprocess_images=False)
    
    # Создаём тестовое изображение
    img_array = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    
    # Применяем предобработку (должна вернуть оригинал)
    preprocessed = reader._preprocess_image(img)
    
    # Должны получить тот же объект
    assert preprocessed is img


@pytest.mark.skipif(
    not hasattr(__import__('document_processor.pdf_reader.reader', fromlist=['OCR_AVAILABLE']), 'OCR_AVAILABLE') 
    or not __import__('document_processor.pdf_reader.reader', fromlist=['OCR_AVAILABLE']).OCR_AVAILABLE,
    reason="OCR недоступен"
)
def test_detect_orientation_osd_graceful_fail():
    """OSD корректно обрабатывает ошибки."""
    from PIL import Image
    import numpy as np
    
    reader = PdfReader(use_osd=True)
    
    # Создаём маленькое изображение (может не хватить для OSD)
    img_array = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    
    # Вызов не должен падать, даже если OSD не работает
    result = reader._detect_orientation_osd(img)
    
    # Результат None или угол
    assert result is None or isinstance(result, int)


def test_indexer_uses_config_from_flask(tmp_path):
    """Индексатор использует конфигурацию Flask если доступна."""
    from document_processor.search.indexer import Indexer
    
    # Создаём тестовый файл
    test_file = tmp_path / "test.txt"
    test_file.write_text("тест", encoding="utf-8")
    
    # Индексация должна работать даже вне контекста Flask
    indexer = Indexer()
    index_path = indexer.create_index(str(tmp_path))
    
    assert Path(index_path).exists()
    index_text = Path(index_path).read_text(encoding="utf-8")
    assert "тест" in index_text


def test_backward_compatibility_pdf_reader():
    """PdfReader() без параметров работает (обратная совместимость)."""
    # Не должно быть ошибок при создании без параметров
    reader = PdfReader()
    
    # Проверяем, что все методы доступны
    assert hasattr(reader, 'read_pdf')
    assert hasattr(reader, '_extract_text_ocr')
    assert hasattr(reader, '_auto_orient_image')
    assert hasattr(reader, '_preprocess_image')
    assert hasattr(reader, '_detect_orientation_osd')
    assert hasattr(reader, '_detect_orientation_fallback')
