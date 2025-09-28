import io
import zipfile
import pytest
from pathlib import Path
from document_processor import DocumentProcessor


def test_zip_archive_indexing(tmp_path: Path):
    root = tmp_path / 'root'
    root.mkdir()
    # Создаем zip с парой файлов внутри папок
    zpath = root / 'a.zip'
    with zipfile.ZipFile(zpath, 'w') as z:
        z.writestr('docs/readme.txt', 'тест внутри архива')
        z.writestr('docs/note.docx', b'PK\x03\x04')  # заглушка, будет пропущен/пустой

    dp = DocumentProcessor()
    index_path = dp.create_search_index(str(root))

    text = (root / '_search_index.txt').read_text(encoding='utf-8', errors='ignore')
    assert 'zip://a.zip!/docs/readme.txt' in text
    assert 'тест внутри архива' in text


@pytest.mark.skipif(__import__('shutil').which('unrar') is None, reason='unrar not installed')
def test_rar_archive_indexing(tmp_path: Path):
    root = tmp_path / 'root'
    root.mkdir()
    # Подготовка RAR архива программно не тривиальна без внешних утилит; пропустим генерацию
    # В smoke-режиме проверим graceful-degrade: пустая индексация не падает
    (root / 'placeholder.txt').write_text('ок', encoding='utf-8')
    dp = DocumentProcessor()
    dp.create_search_index(str(root))
    assert (root / '_search_index.txt').exists()
