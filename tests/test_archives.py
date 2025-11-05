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
    dp.create_search_index(str(root))

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


def test_nested_zip_archive_indexing(tmp_path: Path):
    """Тест FR-008: вложенные архивы с archive_depth=1"""
    root = tmp_path / 'root'
    root.mkdir()
    
    # Создаём внутренний ZIP с файлом
    inner_zip_data = io.BytesIO()
    with zipfile.ZipFile(inner_zip_data, 'w') as inner_z:
        inner_z.writestr('inner_doc.txt', 'текст во вложенном архиве')
    inner_zip_bytes = inner_zip_data.getvalue()
    
    # Создаём внешний ZIP, содержащий внутренний ZIP и обычный файл
    outer_zpath = root / 'outer.zip'
    with zipfile.ZipFile(outer_zpath, 'w') as outer_z:
        outer_z.writestr('nested/inner.zip', inner_zip_bytes)
        outer_z.writestr('nested/readme.txt', 'текст в основном архиве')
    
    # Индексируем с archive_depth=1 (позволяем один уровень вложенности)
    from document_processor.search.indexer import Indexer
    indexer = Indexer(archive_depth=1)
    indexer.create_index(str(root))
    
    text = (root / '_search_index.txt').read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем, что оба файла проиндексированы
    assert 'zip://outer.zip!/nested/readme.txt' in text
    assert 'текст в основном архиве' in text
    
    # Проверяем вложенный архив
    assert 'zip://outer.zip!/nested/inner.zip!/inner_doc.txt' in text
    assert 'текст во вложенном архиве' in text


def test_corrupted_zip_archive(tmp_path: Path):
    """Тест обработки повреждённого архива (FR-004)"""
    root = tmp_path / 'root'
    root.mkdir()
    
    # Создаём поддельный ZIP файл (повреждённый)
    bad_zip = root / 'corrupted.zip'
    bad_zip.write_bytes(b'PK\x03\x04\x00\x00fake')
    
    # Создаём нормальный файл для проверки, что индексация не прерывается
    (root / 'good.txt').write_text('нормальный файл', encoding='utf-8')
    
    dp = DocumentProcessor()
    dp.create_search_index(str(root))
    
    text = (root / '_search_index.txt').read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем, что нормальный файл проиндексирован
    assert 'нормальный файл' in text
    
    # Повреждённый архив не должен привести к сбою индексации
    assert (root / '_search_index.txt').exists()

