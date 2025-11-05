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


@pytest.fixture
def app():
    """Создание минимального Flask app для контекста."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


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


def test_calculate_file_hash_nonexistent(app):
    """Тест обработки несуществующего файла."""
    from webapp.services.db_indexing import calculate_file_hash
    
    with app.app_context():
        result = calculate_file_hash('/nonexistent/file/path.txt')
        
        # Функция должна вернуть пустую строку при ошибке
        assert result == ""


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
    
    # Мокаем запрос к БД (только id, root_hash, last_indexed_at)
    mock_cursor.fetchone.return_value = (
        1,  # id
        'abc123hash',  # root_hash
        datetime.now()  # last_indexed_at
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Вызываем функцию
    status = get_folder_index_status(mock_db, owner_id=1, folder_path='/test/folder')
    
    # Проверяем результат
    assert status is not None
    assert status['id'] == 1
    assert status['root_hash'] == 'abc123hash'
    assert 'last_indexed_at' in status
    

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
    
    # Мокаем результат: документ существует (id, owner_id, original_filename, is_visible, deleted_at, sha256)
    mock_cursor.fetchone.return_value = (
        123,  # id
        1,  # owner_id
        'test.txt',  # original_filename
        True,  # is_visible
        None,  # deleted_at
        'abc123'  # sha256
    )
    
    mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_db.db.connect.return_value = mock_conn
    
    # Проверяем существующий документ (требуется app_context)
    from flask import Flask
    app = Flask(__name__)
    with app.app_context():
        result = check_document_exists_by_hash(mock_db, sha256_hash='abc123')
    
    assert result is not None
    assert result['id'] == 123
    assert result['is_visible'] is True


@patch('webapp.services.db_indexing.RAGDatabase')
def test_handle_duplicate_upload_new_doc(mock_db, tmp_path):
    """Тест: новый документ индексируется обычным образом"""
    from webapp.services.db_indexing import calculate_file_hash, handle_duplicate_upload
    
    test_file = tmp_path / "test.txt"
    test_file.write_text("Новый документ", encoding='utf-8')
    
    sha256 = calculate_file_hash(str(test_file))
    
    with patch('webapp.services.db_indexing.check_document_exists_by_hash', return_value=None), \
         patch('webapp.services.db_indexing.index_document_to_db', return_value=(123, 0.5)):
        
        doc_id, msg, is_dup = handle_duplicate_upload(
            mock_db, owner_id=1, file_path=str(test_file), sha256_hash=sha256
        )
    
    assert doc_id == 123
    assert msg == 'Новый документ проиндексирован'
    assert is_dup is False


def test_handle_duplicate_upload_existing_visible(app, tmp_path):
    """Тест: документ уже существует у пользователя и видим → пропускаем"""
    from webapp.services.db_indexing import calculate_file_hash, handle_duplicate_upload
    
    test_file = tmp_path / "test.txt"
    test_file.write_text("Существующий документ", encoding='utf-8')
    
    with app.app_context():
        sha256 = calculate_file_hash(str(test_file))
        existing = {'id': 456, 'owner_id': 1, 'is_visible': True}
        
        mock_db = Mock()
        
        with patch('webapp.services.db_indexing.check_document_exists_by_hash', return_value=existing):
            doc_id, msg, is_dup = handle_duplicate_upload(
                mock_db, owner_id=1, file_path=str(test_file), sha256_hash=sha256
            )
        
        assert doc_id == 456
        assert 'уже существует' in msg.lower()
        assert is_dup is True


def test_handle_duplicate_upload_soft_deleted(app, tmp_path):
    """Тест: документ мягко удалён у того же пользователя → восстанавливаем"""
    from webapp.services.db_indexing import calculate_file_hash, handle_duplicate_upload
    
    test_file = tmp_path / "test.txt"
    test_file.write_text("Удалённый документ", encoding='utf-8')
    
    with app.app_context():
        sha256 = calculate_file_hash(str(test_file))
        existing = {'id': 789, 'owner_id': 1, 'is_visible': False}
        
        mock_db = Mock()
        
        with patch('webapp.services.db_indexing.check_document_exists_by_hash', return_value=existing), \
             patch('webapp.services.db_indexing.restore_soft_deleted_document', return_value=True):
            
            doc_id, msg, is_dup = handle_duplicate_upload(
                mock_db, owner_id=1, file_path=str(test_file), sha256_hash=sha256
            )
        
        assert doc_id == 789
        assert 'восстановлен' in msg.lower()
        assert is_dup is True


def test_handle_duplicate_upload_other_user(app, tmp_path):
    """Тест: документ существует у другого пользователя → создаём новую запись"""
    from webapp.services.db_indexing import calculate_file_hash, handle_duplicate_upload
    
    test_file = tmp_path / "test.txt"
    test_file.write_text("Документ другого пользователя", encoding='utf-8')
    
    with app.app_context():
        sha256 = calculate_file_hash(str(test_file))
        existing = {'id': 100, 'owner_id': 2, 'is_visible': True}  # owner_id=2
        
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [200]  # new_doc_id
        
        # Правильная настройка моков
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.commit = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        
        mock_db.db.connect = Mock(return_value=mock_conn)
        
        with patch('webapp.services.db_indexing.check_document_exists_by_hash', return_value=existing), \
             patch('webapp.services.db_indexing.copy_chunks_between_users', return_value=10):
            
            doc_id, msg, is_dup = handle_duplicate_upload(
                mock_db, owner_id=1, file_path=str(test_file), sha256_hash=sha256
            )
        
        assert doc_id == 200
        assert 'нового пользователя' in msg.lower()
        assert is_dup is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
