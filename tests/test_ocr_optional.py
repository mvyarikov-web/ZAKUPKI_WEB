import os
from pathlib import Path
import pytest

from document_processor import DocumentProcessor


@pytest.mark.skipif(
    not (os.environ.get("TESSERACT_AVAILABLE") == "1"),
    reason="OCR-зависимости не установлены; включите TESSERACT_AVAILABLE=1 чтобы выполнить тест"
)
def test_ocr_best_effort_docx(tmp_path: Path):
    # Подготовим docx с картинкой — для простоты используем заглушку: если окружение не готово, тест пропускается
    # Здесь мы имитируем наличие docx с изображением: создаём пустой docx и проверяем, что индексация не падает
    root = tmp_path / "root"
    root.mkdir()
    f = root / "image_only.docx"
    # Минимальный docx — это zip, создадим пустышку
    import zipfile
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))
    assert os.path.exists(index_path)
    data = Path(index_path).read_text(encoding='utf-8')
    assert 'ЗАГОЛОВОК: image_only.docx' in data
