from pathlib import Path
from document_processor import DocumentProcessor


def test_xlsx_text_present_in_index(tmp_path, make_xlsx):
    root: Path = tmp_path / "root"
    root.mkdir()
    # создаём XLSX с одной ячейкой
    xlsx_path = make_xlsx("sample.xlsx", [(1, 1, "эксель-тест")])
    # перемещаем в root, чтобы индексатор его увидел
    (root / xlsx_path.name).write_bytes(xlsx_path.read_bytes())

    dp = DocumentProcessor()
    dp.create_search_index(str(root))

    text = (root / "_search_index.txt").read_text(encoding="utf-8", errors="ignore")
    assert "Лист:" in text  # заголовок листа присутствует
    assert "эксель-тест" in text  # содержимое ячейки присутствует в индексе
