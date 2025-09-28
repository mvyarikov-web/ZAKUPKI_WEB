from pathlib import Path
from document_processor import DocumentProcessor


def test_search_ignores_headers(make_root, make_txt):
    root: Path = make_root
    (root / "file.txt").write_text("Тут сказано: ЖИРАФ. Ещё раз: жираф.", encoding="utf-8")

    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))

    results = dp.search_keywords(index_path, ["жираф"], context=12)
    assert results, "Не найдено совпадений"

    for r in results:
        snippet = r.get("snippet", "")
        assert "====" not in snippet and "Format:" not in snippet
        assert "жираф".lower() in snippet.lower()
