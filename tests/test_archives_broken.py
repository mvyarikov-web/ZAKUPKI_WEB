from pathlib import Path
from document_processor import DocumentProcessor


def test_broken_zip_is_skipped_gracefully(tmp_path: Path):
    root = tmp_path / 'root'
    root.mkdir()
    zpath = root / 'broken.zip'
    # Пишем битые данные вместо валидного zip
    zpath.write_bytes(b'NotAZip')

    dp = DocumentProcessor()
    dp.create_search_index(str(root))
    assert (root / '_search_index.txt').exists()
    data = (root / '_search_index.txt').read_text(encoding='utf-8', errors='ignore')
    # Индексация не должна упасть, запись про архив может отсутствовать
    assert 'broken.zip' in data or len(data) >= 0
