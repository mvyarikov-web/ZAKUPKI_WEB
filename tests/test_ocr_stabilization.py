"""Тесты для стабилизации OCR (increment-013, Этап 1)."""
import pytest
from unittest.mock import Mock, patch


@pytest.mark.timeout(10)
def test_ocr_timeout_configuration():
    """Проверка, что параметр OCR_TIMEOUT_PER_PAGE применяется из конфигурации."""
    from document_processor.pdf_reader import PdfReader
    from webapp.config import Config
    
    reader = PdfReader()
    
    # Проверяем, что можем получить конфиг
    timeout = reader._get_config_value('OCR_TIMEOUT_PER_PAGE', 30)
    assert timeout == Config.OCR_TIMEOUT_PER_PAGE
    assert timeout == 30  # дефолтное значение


@pytest.mark.timeout(10)
def test_ocr_preprocess_disabled_by_default():
    """Проверка, что предобработка отключена по умолчанию."""
    from webapp.config import Config
    
    assert not Config.OCR_PREPROCESS_ENABLED


@pytest.mark.timeout(10)
def test_ocr_per_page_error_handling(tmp_path, monkeypatch):
    """Проверка, что ошибка на одной странице не роняет весь процесс OCR."""
    from document_processor.pdf_reader import PdfReader
    
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    # Мокируем pdf2image и pytesseract
    mock_images = [Mock(), Mock(), Mock()]  # 3 страницы
    
    call_count = [0]
    
    def mock_image_to_string(img, lang=None, timeout=None):
        # Первая страница - успешно, вторая - ошибка, третья - успешно
        call_count[0] += 1
        if call_count[0] == 1:
            return "Текст страницы 1"
        elif call_count[0] == 2:
            raise RuntimeError("Timeout превышен")
        elif call_count[0] == 3:
            return "Текст страницы 3"
        return ""
    
    # Создаём мок-модуль для pytesseract
    mock_pytesseract = Mock()
    mock_pytesseract.image_to_string = mock_image_to_string
    
    # Патчим на уровне модуля, где OCR_AVAILABLE = True
    with patch('document_processor.pdf_reader.reader.OCR_AVAILABLE', True):
        with patch('document_processor.pdf_reader.reader.convert_from_path', return_value=mock_images):
            with patch('document_processor.pdf_reader.reader.pytesseract', mock_pytesseract):
                reader = PdfReader()
                text, attempts = reader._extract_text_ocr(
                    str(pdf_path), max_pages=3, lang='rus+eng', timeout_per_page=5
                )
    
    # Должны получить текст из страниц 1 и 3 (страница 2 пропущена)
    assert "Текст страницы 1" in text
    assert "Текст страницы 3" in text
    assert len(attempts) == 1
    assert attempts[0]['ok']


@pytest.mark.timeout(10)
def test_ocr_dependencies_not_available(tmp_path, monkeypatch):
    """Проверка graceful degradation при отсутствии OCR-зависимостей."""
    from document_processor.pdf_reader import PdfReader
    
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    # Симулируем отсутствие OCR
    with patch('document_processor.pdf_reader.reader.OCR_AVAILABLE', False):
        reader = PdfReader()
        text, attempts = reader._extract_text_ocr(
            str(pdf_path), max_pages=2, lang='rus+eng'
        )
    
    # Должны получить пустой текст и попытку с ошибкой
    assert text == ''
    assert len(attempts) == 1
    assert not attempts[0]['ok']
    assert 'not available' in attempts[0]['error']


@pytest.mark.timeout(10)
def test_ocr_logs_per_page(tmp_path, caplog):
    """Проверка, что OCR логирует обработку каждой страницы."""
    from document_processor.pdf_reader import PdfReader
    import logging
    
    caplog.set_level(logging.DEBUG)
    
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    # Мокируем pdf2image и pytesseract
    mock_images = [Mock(), Mock()]
    
    mock_pytesseract = Mock()
    mock_pytesseract.image_to_string = Mock(return_value="Тестовый текст")
    
    with patch('document_processor.pdf_reader.reader.OCR_AVAILABLE', True):
        with patch('document_processor.pdf_reader.reader.convert_from_path', return_value=mock_images):
            with patch('document_processor.pdf_reader.reader.pytesseract', mock_pytesseract):
                reader = PdfReader()
                text, attempts = reader._extract_text_ocr(
                    str(pdf_path), max_pages=2, lang='rus+eng', timeout_per_page=10
                )
    
    # Проверяем логи
    log_messages = [record.message for record in caplog.records]
    assert any("OCR страницы 1" in msg for msg in log_messages)
    assert any("OCR страницы 2" in msg for msg in log_messages)
    assert any("OCR завершён" in msg for msg in log_messages)


@pytest.mark.timeout(10) 
def test_preprocess_image_graceful_fail(tmp_path):
    """Проверка, что ошибка в предобработке не ломает OCR."""
    from document_processor.pdf_reader import PdfReader
    
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    mock_img = Mock()
    
    # Мокируем предобработку, которая падает
    def mock_preprocess_fail(img):
        raise ValueError("Ошибка предобработки")
    
    mock_pytesseract = Mock()
    mock_pytesseract.image_to_string = Mock(return_value="Текст после OCR")
    
    with patch('document_processor.pdf_reader.reader.OCR_AVAILABLE', True):
        with patch('document_processor.pdf_reader.reader.convert_from_path', return_value=[mock_img]):
            with patch('document_processor.pdf_reader.reader.pytesseract', mock_pytesseract):
                # Включаем предобработку через конфиг
                with patch.object(PdfReader, '_get_config_value', side_effect=lambda k, d: True if k == 'OCR_PREPROCESS_ENABLED' else d):
                    # Патчим импорт внутри метода
                    with patch('document_processor.pdf_reader.image_utils.preprocess_image_for_ocr', side_effect=mock_preprocess_fail):
                        reader = PdfReader()
                        text, attempts = reader._extract_text_ocr(
                            str(pdf_path), max_pages=1, lang='rus+eng'
                        )
    
    # OCR должен продолжить работу с исходным изображением
    assert "Текст после OCR" in text
    assert attempts[0]['ok']


@pytest.mark.timeout(10)
def test_image_utils_preprocess_basic():
    """Базовая проверка функции предобработки изображений."""
    try:
        from PIL import Image
        from document_processor.pdf_reader.image_utils import preprocess_image_for_ocr
        
        # Создаём простое тестовое изображение
        img = Image.new('RGB', (100, 100), color='white')
        
        # Предобработка не должна падать
        result = preprocess_image_for_ocr(img)
        
        assert result is not None
        assert isinstance(result, Image.Image)
        
    except ImportError:
        pytest.skip("PIL не установлен")


@pytest.mark.timeout(10)
def test_image_utils_preprocess_without_pil():
    """Проверка graceful degradation при отсутствии PIL."""
    from document_processor.pdf_reader.image_utils import preprocess_image_for_ocr, PIL_AVAILABLE
    
    if PIL_AVAILABLE:
        pytest.skip("PIL установлен, тест не применим")
    
    # Должна вернуть исходное изображение без падения
    mock_img = Mock()
    result = preprocess_image_for_ocr(mock_img)
    assert result == mock_img


@pytest.mark.timeout(10)
def test_config_values_added():
    """Проверка, что новые конфигурационные параметры добавлены."""
    from webapp.config import Config
    
    # Все параметры из increment-013 должны быть добавлены
    assert hasattr(Config, 'OCR_TIMEOUT_PER_PAGE')
    assert hasattr(Config, 'OCR_PREPROCESS_ENABLED')
    assert hasattr(Config, 'OCR_USE_OSD')
    assert hasattr(Config, 'OCR_PARALLEL_PAGES')
    assert hasattr(Config, 'OCR_MAX_WORKERS')
    
    # Проверка дефолтных значений
    assert Config.OCR_TIMEOUT_PER_PAGE == 30
    assert not Config.OCR_PREPROCESS_ENABLED
    assert not Config.OCR_USE_OSD
    assert not Config.OCR_PARALLEL_PAGES
    assert Config.OCR_MAX_WORKERS == 4


@pytest.mark.timeout(10)
def test_ocr_timeout_passed_to_pytesseract(tmp_path):
    """Проверка, что timeout передаётся в pytesseract.image_to_string."""
    from document_processor.pdf_reader import PdfReader
    
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    
    mock_img = Mock()
    timeout_used = [None]
    
    def capture_timeout(img, lang=None, timeout=None):
        timeout_used[0] = timeout
        return "Текст"
    
    mock_pytesseract = Mock()
    mock_pytesseract.image_to_string = capture_timeout
    
    with patch('document_processor.pdf_reader.reader.OCR_AVAILABLE', True):
        with patch('document_processor.pdf_reader.reader.convert_from_path', return_value=[mock_img]):
            with patch('document_processor.pdf_reader.reader.pytesseract', mock_pytesseract):
                reader = PdfReader()
                text, attempts = reader._extract_text_ocr(
                    str(pdf_path), max_pages=1, lang='rus+eng', timeout_per_page=15
                )
    
    # Проверяем, что timeout был передан
    assert timeout_used[0] == 15
