"""Тесты для утилит работы с виртуальными путями архивов."""
import zipfile
from pathlib import Path
from webapp.services.archives import (
    parse_virtual_path,
    is_archive_path,
    get_archive_root,
    list_archive_contents,
    sanitize_archive_path
)


def test_parse_virtual_path():
    """Тест парсинга виртуальных путей."""
    # Обычный файл
    scheme, segments = parse_virtual_path('file.txt')
    assert scheme is None
    assert segments == []
    
    # Простой архив
    scheme, segments = parse_virtual_path('zip://a.zip!/doc.txt')
    assert scheme == 'zip'
    assert len(segments) == 1
    assert segments[0] == ('a.zip', 'doc.txt')
    
    # Вложенный архив
    scheme, segments = parse_virtual_path('zip://outer.zip!/inner.zip!/doc.txt')
    assert scheme == 'zip'
    assert len(segments) == 2


def test_is_archive_path():
    """Тест проверки виртуальных путей."""
    assert is_archive_path('zip://a.zip!/doc.txt')
    assert is_archive_path('rar://b.rar!/doc.txt')
    assert not is_archive_path('file.txt')
    assert not is_archive_path('http://example.com/file.txt')


def test_get_archive_root():
    """Тест извлечения корневого архива."""
    assert get_archive_root('zip://a.zip!/doc.txt') == 'a.zip'
    assert get_archive_root('zip://outer.zip!/inner.zip!/doc.txt') == 'outer.zip'
    assert get_archive_root('file.txt') is None


def test_list_archive_contents(tmp_path: Path):
    """Тест получения содержимого архива."""
    base_dir = tmp_path / 'uploads'
    base_dir.mkdir()
    
    # Создаём архив с файлами в разных папках
    archive_path = base_dir / 'test.zip'
    with zipfile.ZipFile(archive_path, 'w') as z:
        z.writestr('docs/readme.txt', 'test content')
        z.writestr('docs/guide.pdf', b'PDF content')
        z.writestr('data/file.csv', 'csv data')
    
    entries = list_archive_contents('test.zip', str(base_dir))
    
    # Должны быть виртуальные папки и файлы
    assert len(entries) > 0
    
    # Проверяем наличие файлов
    file_paths = [e.path for e in entries if not e.is_virtual_folder]
    assert 'zip://test.zip!/docs/readme.txt' in file_paths
    assert 'zip://test.zip!/docs/guide.pdf' in file_paths
    assert 'zip://test.zip!/data/file.csv' in file_paths


def test_list_corrupted_archive(tmp_path: Path):
    """Тест обработки повреждённого архива."""
    base_dir = tmp_path / 'uploads'
    base_dir.mkdir()
    
    # Создаём фейковый ZIP
    bad_archive = base_dir / 'bad.zip'
    bad_archive.write_bytes(b'PK\x03\x04\x00\x00fake')
    
    entries = list_archive_contents('bad.zip', str(base_dir))
    
    # Должна вернуться одна запись с ошибкой
    assert len(entries) == 1
    assert entries[0].status == 'error'
    assert 'Повреждённый' in entries[0].error


def test_sanitize_archive_path():
    """Тест защиты от ZipSlip (FR-006)."""
    # Нормальные пути
    assert sanitize_archive_path('docs/file.txt') == 'docs/file.txt'
    assert sanitize_archive_path('file.txt') == 'file.txt'
    
    # Попытки обхода директорий
    assert sanitize_archive_path('../../../etc/passwd') == 'etc/passwd'
    assert sanitize_archive_path('docs/../../../etc/passwd') == 'etc/passwd'
    
    # Абсолютные пути
    assert sanitize_archive_path('/etc/passwd') == 'etc/passwd'
    
    # Точки в пути
    assert sanitize_archive_path('./docs/./file.txt') == 'docs/file.txt'
