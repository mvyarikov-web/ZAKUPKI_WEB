import os
from pathlib import Path

from document_processor import DocumentProcessor
from document_processor.search.searcher import Searcher


def test_indexer_recurses_nested_dirs(tmp_path: Path):
    root = tmp_path / "root"
    nested = root / "a" / "b" / "c"
    nested.mkdir(parents=True)

    # Создаём файл глубоко во вложенных папках
    f = nested / "test.txt"
    text = "Это тестовый текст о жирафе в лесу."
    f.write_text(text, encoding="utf-8")

    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))

    # Индекс должен создаться в корне
    assert os.path.basename(index_path) == "_search_index.txt"
    assert os.path.exists(index_path)

    # В индексе должен быть заголовок с относительным путём
    index_data = Path(index_path).read_text(encoding="utf-8")
    assert "ЗАГОЛОВОК: a/b/c/test.txt" in index_data.replace("\\", "/")

    # Поиск по индексу находит фразу из файла
    s = Searcher()
    results = s.search(index_path, ["жираф", "лес"], context=40)
    assert any("жираф" in r.get("snippet", "").lower() for r in results)
    assert any(r.get("title", "").endswith("a/b/c/test.txt") for r in results)
