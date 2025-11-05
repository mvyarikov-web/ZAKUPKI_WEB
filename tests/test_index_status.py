"""Тесты для менеджера прогресса индексации (increment-013, Этап 4)."""
import json
import pytest


@pytest.mark.timeout(30)
def test_status_file_created_during_indexing(tmp_path):
    """Проверка, что файл статуса создаётся во время индексации."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    
    # Создаём тестовый файл
    (root / "test.txt").write_text("Тестовый контент", encoding='utf-8')
    
    indexer = Indexer()
    indexer.create_index(str(root))
    
    # Проверяем, что status.json создан
    status_path = index_dir / "status.json"
    assert status_path.exists(), "Файл status.json должен быть создан"
    
    # Проверяем структуру
    with open(status_path, 'r', encoding='utf-8') as f:
        status = json.load(f)
    
    assert 'status' in status
    assert 'total' in status
    assert 'processed' in status
    assert status['status'] == 'completed'
    assert status['processed'] == status['total']


@pytest.mark.timeout(30)
def test_status_structure_valid(tmp_path):
    """Проверка структуры JSON статуса."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    
    (root / "file1.txt").write_text("Текст 1", encoding='utf-8')
    (root / "file2.pdf").write_bytes(b"%PDF-1.4\n%EOF")
    
    indexer = Indexer()
    indexer.create_index(str(root))
    
    status_path = index_dir / "status.json"
    with open(status_path, 'r', encoding='utf-8') as f:
        status = json.load(f)
    
    # Проверяем обязательные поля
    required_fields = ['status', 'total', 'processed', 'updated_at']
    for field in required_fields:
        assert field in status, f"Поле {field} должно быть в статусе"
    
    # Проверяем, что статус завершён
    assert status['status'] == 'completed'
    assert status['total'] == 2  # 2 файла
    assert status['processed'] == 2


@pytest.mark.timeout(30)
def test_flask_index_status_endpoint(tmp_path):
    """Проверка эндпоинта /index_status в Flask."""
    from webapp import create_app
    
    # Создаём приложение с временной конфигурацией
    app = create_app('testing')
    app.config['INDEX_FOLDER'] = str(tmp_path / 'index')
    app.config['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    
    # Создаём директории
    (tmp_path / 'index').mkdir()
    (tmp_path / 'uploads').mkdir()
    
    with app.test_client() as client:
        # Тест 1: Без файла статуса должен вернуть exists=False
        response = client.get('/index_status')
        assert response.status_code == 200
        data = response.get_json()
        assert not data['exists']
        
        # Тест 2: С файлом статуса прогресса
        status_path = tmp_path / 'index' / 'status.json'
        status_data = {
            'status': 'running',
            'total': 10,
            'processed': 5,
            'current_file': 'test.pdf',
            'current_format': 'PDF',
            'ocr_active': True,
            'updated_at': '2025-10-19T12:00:00'
        }
        
        import json
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status_data, f)
        
        response = client.get('/index_status')
        assert response.status_code == 200
        data = response.get_json()
        # Статус прогресса должен быть в поле 'progress'
        assert 'progress' in data
        assert data['progress']['status'] == 'running'
        assert data['progress']['total'] == 10
        assert data['progress']['processed'] == 5
        assert data['progress']['current_file'] == 'test.pdf'
        assert data['progress']['ocr_active']


@pytest.mark.timeout(30)
def test_status_updates_during_processing(tmp_path):
    """Проверка, что статус обновляется в процессе обработки файлов."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    
    # Создаём несколько файлов
    (root / "file1.txt").write_text("Текст 1", encoding='utf-8')
    (root / "file2.txt").write_text("Текст 2", encoding='utf-8')
    (root / "file3.pdf").write_bytes(b"%PDF-1.4\n%EOF")
    
    status_path = index_dir / "status.json"
    snapshots = []
    
    indexer = Indexer()
    original_write = indexer._write_entry
    
    def tracked_write_entry(*args, **kwargs):
        # Снимаем снимок статуса
        if status_path.exists():
            with open(status_path, 'r', encoding='utf-8') as f:
                snapshots.append(json.load(f))
        return original_write(*args, **kwargs)
    
    indexer._write_entry = tracked_write_entry
    indexer.create_index(str(root))
    
    # Должны были быть промежуточные обновления
    assert len(snapshots) > 0, "Статус должен обновляться во время индексации"
    
    # Проверяем, что processed увеличивается
    processed_values = [s.get('processed', 0) for s in snapshots if 'processed' in s]
    assert len(processed_values) > 0
    # Проверяем монотонность (не строго, т.к. может быть несколько записей с одним значением)
    for i in range(1, len(processed_values)):
        assert processed_values[i] >= processed_values[i-1]


@pytest.mark.timeout(30)
def test_status_error_handling(tmp_path):
    """Проверка обработки ошибок в статусе."""
    from document_processor.search.indexer import Indexer
    from unittest.mock import patch
    
    root = tmp_path / "uploads"
    root.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    
    (root / "test.txt").write_text("Тест", encoding='utf-8')
    
    indexer = Indexer()
    
    # Симулируем ошибку при извлечении текста
    with patch.object(indexer, '_extract_text', side_effect=RuntimeError("Test error")):
        try:
            indexer.create_index(str(root))
        except RuntimeError:
            pass  # ожидаем ошибку
    
    # Проверяем, что статус содержит информацию об ошибке
    status_path = index_dir / "status.json"
    if status_path.exists():
        with open(status_path, 'r', encoding='utf-8') as f:
            status = json.load(f)
        assert status['status'] == 'error'
        assert 'error' in status


@pytest.mark.timeout(30)
def test_status_timestamps(tmp_path):
    """Проверка, что временные метки корректно записываются."""
    from document_processor.search.indexer import Indexer
    from datetime import datetime
    
    root = tmp_path / "uploads"
    root.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    
    (root / "test.txt").write_text("Тест", encoding='utf-8')
    
    before = datetime.now()
    
    indexer = Indexer()
    indexer.create_index(str(root))
    
    after = datetime.now()
    
    status_path = index_dir / "status.json"
    with open(status_path, 'r', encoding='utf-8') as f:
        status = json.load(f)
    
    # Проверяем наличие временных меток
    assert 'started_at' in status
    assert 'updated_at' in status
    
    # Проверяем, что временные метки валидны (можно распарсить)
    started = datetime.fromisoformat(status['started_at'])
    updated = datetime.fromisoformat(status['updated_at'])
    
    # Временные метки должны быть в разумном диапазоне
    assert before <= started <= after
    assert before <= updated <= after


@pytest.mark.timeout(30)
def test_collect_all_files_method(tmp_path):
    """Проверка метода _collect_all_files для подсчёта файлов."""
    from document_processor.search.indexer import Indexer
    
    root = tmp_path / "uploads"
    root.mkdir()
    
    # Создаём файлы
    (root / "file1.txt").write_text("1", encoding='utf-8')
    (root / "file2.pdf").write_bytes(b"%PDF-1.4\n%EOF")
    (root / "file3.docx").write_text("3", encoding='utf-8')
    
    indexer = Indexer()
    all_files = indexer._collect_all_files(str(root))
    
    # Должны собрать все файлы
    assert len(all_files) == 3
    
    # Проверяем структуру
    assert all(len(f) == 4 for f in all_files)  # (ext, name, abs_path, rel_path)
    
    # Проверяем, что расширения правильные
    extensions = set(f[0] for f in all_files)
    assert extensions == {'txt', 'pdf', 'docx'}
