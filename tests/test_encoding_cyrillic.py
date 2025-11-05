from pathlib import Path
from document_processor import DocumentProcessor


def test_txt_cp1251_and_cp866(tmp_path: Path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'u8.txt').write_text('Привет, мир!', encoding='utf-8')
    (root / 'cp1251.txt').write_bytes('Привет, мир!'.encode('cp1251', errors='ignore'))
    (root / 'cp866.txt').write_bytes('Привет, мир!'.encode('cp866', errors='ignore'))

    DocumentProcessor().create_search_index(str(root))
    text = (root / '_search_index.txt').read_text(encoding='utf-8', errors='ignore')

    assert 'Привет' in text
    assert 'мир' in text
