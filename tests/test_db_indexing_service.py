"""
Тесты для сервиса db_indexing.py

Проверяется:
- Расчёт хешей файлов и папок
- Инкрементальная индексация (root_hash)
- Обработка дубликатов (4 сценария)
- Восстановление мягко удалённых документов
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Для тестов с БД нужно использовать реальное подключение или мок
# Упрощённо: используем моки для изоляции тестов


def test_calculate_file_hash():
    """Тест расчёта SHA256 хеша файла."""
    from webapp.services.db_indexing import calculate_file_hash
    
    # Создаём временный файл с известным содержимым
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        f.write('Test content for hashing')
        temp_path = f.name
    
    try:
        file_hash = calculate_file_hash(temp_path)
        
        # Проверяем, что хеш не пустой и имеет правильную длину (64 символа для SHA256)
        assert file_hash is not None
        assert len(file_hash) == 64
        assert file_hash.isalnum()
        
        # Проверяем детерминированность: повторный расчёт даёт тот же результат
        file_hash2 = calculate_file_hash(temp_path)
        assert file_hash == file_hash2
    finally:
        os.unlink(temp_path)


def test_calculate_file_hash_nonexistent():
    """Тест обработки несуществующего файла."""
    from webapp.services.db_indexing import calculate_file_hash
    
    result = calculate_file_hash('/nonexistent/file/path.txt')
    
    # Функция должна вернуть None при ошибке
    assert result is None


def test_calculate_root_hash():
    """Тест расчёта root_hash для папки."""
    from webapp.services.db_indexing import calculate_root_hash
    
    # Создаём временную структуру файлов
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Создаём несколько файлов
        file1 = Path(tmp_dir) / 'file1.txt'
        file1.write_text('Content 1', encoding='utf-8')
        
        file2 = Path(tmp_dir) / 'file2.txt'
        file2.write_text('Content 2', encoding='utf-8')
        
        # Создаём вложенную папку
        sub_dir = Path(tmp_dir) / 'subdir'
        sub_dir.mkdir()
        file3 = sub_dir / 'file3.txt'
        file3.write_text('Content 3', encoding='utf-8')
        
        # Рассчитываем root_hash
        root_hash = calculate_root_hash(tmp_dir)
        
        # Проверяем корректность
        assert root_hash is not None
        assert len(root_hash) == 64
        
        # Проверяем детерминированность
        root_hash2 = calculate_root_hash(tmp_dir)
        assert root_hash == root_hash2
        
        # Изменяем файл — хеш должен измениться
        file1.write_text('Modified content', encoding='utf-8')
        root_hash3 = calculate_root_hash(tmp_dir)
        assert root_hash != root_hash3


def test_calculate_root_hash_empty_folder():
    """Тест расчёта хеша для пустой папки."""
    from webapp.services.db_indexing import calculate_root_hash
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        root_hash = calculate_root_hash(tmp_dir)
        
        # Даже для пустой папки должен быть хеш (от пустой строки)
        assert root_hash is not None
        assert len(root_hash) == 64


@patch('webapp.services.db_indexing.RAGDatabase')
def test_get_folder_index_status(mock_db_class):
    """Тест получения статуса индексации папки."""
    from webapp.services.db_indexing import get_folder_index_status
    
    # Настраиваем мок БД
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем запрос к БД
    mock_cursor.fetchone.return_value = (
        1,  # owner_id
        '/test/folder',  # folder_path
        'abc123hash',  # root_hash
        5,  # file_count
        1024000,  # bytes_total
        datetime.now(),  # indexed_at
        datetime.now()  # last_scanned_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Вызываем функцию
    status = get_folder_index_status(mock_db, owner_id=1, folder_path='/test/folder')
    
    # Проверяем результат
    assert status is not None
    assert status['root_hash'] == 'abc123hash'
    assert status['file_count'] == 5
    

@patch('webapp.services.db_indexing.RAGDatabase')
def test_get_folder_index_status_not_found(mock_db_class):
    """Тест получения статуса для неиндексированной папки."""
    from webapp.services.db_indexing import get_folder_index_status
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    status = get_folder_index_status(mock_db, owner_id=1, folder_path='/new/folder')
    
    # Должен вернуть None
    assert status is None


@patch('webapp.services.db_indexing.RAGDatabase')
def test_check_document_exists_by_hash(mock_db_class):
    """Тест проверки существования документа по SHA256."""
    from webapp.services.db_indexing import check_document_exists_by_hash
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Мокаем результат: документ существует
    mock_cursor.fetchone.return_value = (
        123,  # document_id
        1,  # owner_id
        'test.txt',  # original_filename
        True,  # is_visible
        None  # deleted_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Проверяем существующий документ
    result = check_document_exists_by_hash(mock_db, sha256='abc123', owner_id=1)
    
    assert result is not None
    assert result['document_id'] == 123
    assert result['is_visible'] is True


@patch('webapp.services.db_indexing.RAGDatabase')
def test_handle_duplicate_upload_new_file(mock_db_class):
    """Тест обработки нового файла (дубликатов нет)."""
    from webapp.services.db_indexing import handle_duplicate_upload
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Файл не найден в БД
    mock_cursor.fetchone.return_value = None
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    result = handle_duplicate_upload(
        db=mock_db,
        sha256='newhash123',
        owner_id=1,
        file_path='/test/new_file.txt'
    )
    
    # Для нового файла должно вернуться 'new'
    assert result['action'] == 'new'
    assert result['document_id'] is None


@patch('webapp.services.db_indexing.RAGDatabase')
def test_handle_duplicate_upload_existing_visible(mock_db_class):
    """Тест обработки дубликата существующего видимого файла."""
    from webapp.services.db_indexing import handle_duplicate_upload
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Файл найден, видимый
    mock_cursor.fetchone.return_value = (
        100,  # document_id
        1,  # owner_id
        'existing.txt',  # original_filename
        True,  # is_visible
        None  # deleted_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    result = handle_duplicate_upload(
        db=mock_db,
        sha256='existinghash',
        owner_id=1,
        file_path='/test/existing.txt'
    )
    
    # Для существующего должно вернуться 'exists'
    assert result['action'] == 'exists'
    assert result['document_id'] == 100


@patch('webapp.services.db_indexing.RAGDatabase')
@patch('webapp.services.db_indexing.restore_soft_deleted_document')
def test_handle_duplicate_upload_restore_deleted(mock_restore, mock_db_class):
    """Тест восстановления мягко удалённого документа."""
    from webapp.services.db_indexing import handle_duplicate_upload
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Файл найден, но удалён
    mock_cursor.fetchone.return_value = (
        200,  # document_id
        1,  # owner_id
        'deleted.txt',  # original_filename
        False,  # is_visible
        datetime.now()  # deleted_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Мок успешного восстановления
    mock_restore.return_value = True
    
    result = handle_duplicate_upload(
        db=mock_db,
        sha256='deletedhash',
        owner_id=1,
        file_path='/test/deleted.txt'
    )
    
    # Для удалённого должно вернуться 'restored'
    assert result['action'] == 'restored'
    assert result['document_id'] == 200
    mock_restore.assert_called_once()


@patch('webapp.services.db_indexing.RAGDatabase')
@patch('webapp.services.db_indexing.copy_chunks_between_users')
def test_handle_duplicate_upload_other_owner(mock_copy_chunks, mock_db_class):
    """Тест обработки файла, принадлежащего другому пользователю."""
    from webapp.services.db_indexing import handle_duplicate_upload
    
    mock_db = Mock()
    mock_db_class.return_value = mock_db
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Файл найден у другого пользователя
    mock_cursor.fetchone.return_value = (
        300,  # document_id
        2,  # owner_id (другой пользователь)
        'shared.txt',  # original_filename
        True,  # is_visible
        None  # deleted_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Мок копирования чанков
    mock_copy_chunks.return_value = 42  # новый document_id
    
    result = handle_duplicate_upload(
        db=mock_db,
        sha256='sharedhash',
        owner_id=1,  # текущий пользователь
        file_path='/test/shared.txt'
    )
    
    # Для чужого файла должно вернуться 'copied'
    assert result['action'] == 'copied'
    assert result['document_id'] == 42
    assert result['source_document_id'] == 300
    mock_copy_chunks.assert_called_once()


def test_handle_duplicate_upload_graceful_error():
    """Тест graceful degradation при ошибке обработки дубликата."""
    from webapp.services.db_indexing import handle_duplicate_upload
    
    # Передаём некорректные данные
    result = handle_duplicate_upload(
        db=None,  # некорректная БД
        sha256='testhash',
        owner_id=1,
        file_path='/test/file.txt'
    )
    
    # При ошибке должен вернуться 'new' с флагом error
    assert result['action'] == 'new'
    assert 'error' in result or result.get('document_id') is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
