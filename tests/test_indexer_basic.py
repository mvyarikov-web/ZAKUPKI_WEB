from pathlib import Path
from document_processor import DocumentProcessor


def test_index_basic(make_root, make_docx, make_xlsx):
    root: Path = make_root
    (root / "a.txt").write_text("арбуз", encoding="utf-8")
    try:
        make_docx.__wrapped__  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        make_docx("b.docx", ["самолёт"])  # writes into tmp_path; adjust to root if available
    except Exception:
        # если python-docx недоступен — пропускаем часть
        pass
    try:
        make_xlsx("c.xlsx", [(1, 1, "шахматы")])  # writes into tmp_path; таблица опциональна
    except Exception:
        pass

    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))

    assert (root / "_search_index.txt").exists()
    assert str(index_path).endswith("_search_index.txt")

    text = (root / "_search_index.txt").read_text(encoding="utf-8", errors="ignore")
    assert "арбуз" in text
    assert "Формат:" in text and "Символов:" in text and "Источник:" in text
