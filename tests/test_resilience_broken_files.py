import os
from pathlib import Path

from document_processor import DocumentProcessor


def test_broken_pdf_is_handled_gracefully(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    broken = root / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"[:10])

    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))
    assert os.path.exists(index_path)

    data = Path(index_path).read_text(encoding="utf-8")
    # Заголовок на место, тело может быть пустым, но индексация не падает
    assert "ЗАГОЛОВОК: broken.pdf" in data
