"""Тест PDF с реальным файлом (без создания PDF)."""
import pytest
from pathlib import Path
from document_processor.extractors.text_extractor import extract_text, extract_text_from_bytes


def test_pdf_cyrillic_if_exists():
    """Тест PDF с кириллицей - если есть реальный файл в uploads."""
    # Ищем любой PDF файл в uploads
    uploads_dir = Path("uploads")
    if not uploads_dir.exists():
        pytest.skip("uploads/ не существует")
    
    pdf_files = list(uploads_dir.rglob("*.pdf"))
    if not pdf_files:
        pytest.skip("Нет PDF файлов в uploads/ для тестирования")
    
    # Берём первый найденный PDF
    test_pdf = pdf_files[0]
    print(f"\nТестируем PDF: {test_pdf}")
    
    # Тест через файловый путь
    result_path = extract_text(str(test_pdf))
    print(f"Извлечено через путь: {len(result_path)} символов")
    print(f"Первые 200 символов: {result_path[:200]}")
    
    # Тест через bytes
    file_bytes = test_pdf.read_bytes()
    result_bytes = extract_text_from_bytes(file_bytes, 'pdf')
    print(f"Извлечено через bytes: {len(result_bytes)} символов")
    
    # Результаты должны совпадать
    assert result_path == result_bytes, "Результаты извлечения через путь и bytes должны совпадать"
    
    # Проверка на непустоту
    if len(result_path) > 0:
        # Проверка на мусор
        garbage_count = result_path.count('�')
        total_chars = len(result_path)
        garbage_ratio = garbage_count / total_chars if total_chars > 0 else 0
        
        assert garbage_ratio < 0.1, f"Слишком много мусора в результате: {garbage_ratio*100:.1f}%"
        
        # Проверка на наличие кириллицы (если это русский документ)
        cyrillic_count = sum(1 for c in result_path if '\u0400' <= c <= '\u04FF')
        if cyrillic_count > 10:
            print(f"Найдено {cyrillic_count} кириллических символов")
        else:
            print("Документ содержит мало кириллицы (возможно, английский)")
