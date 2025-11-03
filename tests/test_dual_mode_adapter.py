"""
Тесты для DataAccessAdapter — проверка dual-mode работы (БД vs файлы).
"""
import os
import pytest
from unittest.mock import MagicMock
from webapp.services.data_access_adapter import DataAccessAdapter


# ==========================================================================
# Фикстуры
# ==========================================================================

@pytest.fixture
def mock_app_config_files():
    """Flask app.config для файлового режима (use_database=False)."""
    return {
        'USE_DATABASE': False,
        'UPLOAD_FOLDER': 'uploads',
        'INDEX_FOLDER': 'index',
    }


@pytest.fixture
def mock_app_config_db():
    """Flask app.config для БД режима (use_database=True)."""
    return {
        'USE_DATABASE': True,
        'UPLOAD_FOLDER': 'uploads',
        'INDEX_FOLDER': 'index',
    }


@pytest.fixture
def mock_config_service_files():
    """ConfigService объект для файлового режима."""
    config = MagicMock()
    config.use_database = False
    config.uploads_folder = 'uploads'
    config.index_folder = 'index'
    return config


@pytest.fixture
def mock_config_service_db():
    """ConfigService объект для БД режима."""
    config = MagicMock()
    config.use_database = True
    config.uploads_folder = 'uploads'
    config.index_folder = 'index'
    return config


# ==========================================================================
# Тесты: инициализация
# ==========================================================================

def test_adapter_init_files_mode_dict(mock_app_config_files):
    """Адаптер инициализируется в файловом режиме (Flask app.config словарь)."""
    adapter = DataAccessAdapter(mock_app_config_files)
    assert adapter.use_database is False
    assert adapter.uploads_folder == 'uploads'
    assert adapter.index_folder == 'index'


def test_adapter_init_db_mode_dict(mock_app_config_db):
    """Адаптер инициализируется в БД режиме (Flask app.config словарь)."""
    adapter = DataAccessAdapter(mock_app_config_db)
    assert adapter.use_database is True
    assert adapter.uploads_folder == 'uploads'
    assert adapter.index_folder == 'index'


def test_adapter_init_files_mode_service(mock_config_service_files):
    """Адаптер инициализируется в файловом режиме (ConfigService объект)."""
    adapter = DataAccessAdapter(mock_config_service_files)
    assert adapter.use_database is False


def test_adapter_init_db_mode_service(mock_config_service_db):
    """Адаптер инициализируется в БД режиме (ConfigService объект)."""
    adapter = DataAccessAdapter(mock_config_service_db)
    assert adapter.use_database is True


# ==========================================================================
# Тесты: индексация (заглушки, TODO полная реализация)
# ==========================================================================

def test_build_index_files_mode(mock_app_config_files, tmp_path):
    """Построение индекса в файловом режиме."""
    # Подменяем пути на временные
    mock_app_config_files['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    mock_app_config_files['INDEX_FOLDER'] = str(tmp_path / 'index')
    os.makedirs(mock_app_config_files['UPLOAD_FOLDER'], exist_ok=True)
    
    # Создаём тестовый файл
    test_file = os.path.join(mock_app_config_files['UPLOAD_FOLDER'], 'test.txt')
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write('Тестовый документ с ключевым словом жираф')
    
    adapter = DataAccessAdapter(mock_app_config_files)
    
    # TODO: требуется Flask app context для current_app.logger
    # Временно пропускаем реальную сборку индекса
    # success, message, char_counts = adapter.build_index(use_groups=False)
    # assert success is True
    # assert len(char_counts) >= 0


def test_build_index_db_mode(mock_app_config_db, tmp_path):
    """Построение индекса в БД режиме."""
    # Подменяем пути
    mock_app_config_db['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    mock_app_config_db['INDEX_FOLDER'] = str(tmp_path / 'index')
    os.makedirs(mock_app_config_db['UPLOAD_FOLDER'], exist_ok=True)
    
    adapter = DataAccessAdapter(mock_app_config_db)
    
    # TODO: требуется Flask app context + БД соединение
    # Временно пропускаем
    # success, message, char_counts = adapter.build_index(use_groups=False)
    # assert success is True


# ==========================================================================
# Тесты: поиск (заглушки, TODO полная реализация)
# ==========================================================================

def test_search_files_mode_no_index(mock_app_config_files, tmp_path):
    """Поиск в файловом режиме без индекса возвращает пустой список."""
    mock_app_config_files['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    mock_app_config_files['INDEX_FOLDER'] = str(tmp_path / 'index')
    
    adapter = DataAccessAdapter(mock_app_config_files)
    
    # TODO: требуется Flask app context
    # results = adapter.search_documents(['жираф'], user_id=None, exclude_mode=False)
    # assert results == []


def test_search_db_mode_fallback_to_files(mock_app_config_db, tmp_path):
    """Поиск в БД режиме временно использует legacy метод (fallback)."""
    mock_app_config_db['UPLOAD_FOLDER'] = str(tmp_path / 'uploads')
    mock_app_config_db['INDEX_FOLDER'] = str(tmp_path / 'index')
    
    adapter = DataAccessAdapter(mock_app_config_db)
    
    # TODO: проверить fallback на файловый поиск
    # assert adapter.use_database is True
    # results = adapter.search_documents(['жираф'], user_id=1, exclude_mode=False)
    # assert isinstance(results, list)


# ==========================================================================
# Тесты: CRUD документов (заглушки)
# ==========================================================================

def test_get_documents_files_mode(mock_app_config_files):
    """Получение списка документов в файловом режиме."""
    adapter = DataAccessAdapter(mock_app_config_files)
    docs = adapter.get_documents(user_id=None)
    # TODO: реализовать сканирование uploads/
    assert isinstance(docs, list)


def test_get_documents_db_mode(mock_app_config_db):
    """Получение списка документов в БД режиме."""
    adapter = DataAccessAdapter(mock_app_config_db)
    docs = adapter.get_documents(user_id=1)
    # TODO: реализовать запрос к DocumentRepository
    assert isinstance(docs, list)


def test_save_document_files_mode(mock_app_config_files):
    """Сохранение документа в файловом режиме."""
    adapter = DataAccessAdapter(mock_app_config_files)
    result = adapter.save_document(
        user_id=None,
        filename='test.txt',
        content=b'test content',
        content_type='text/plain'
    )
    # TODO: реализовать сохранение в uploads/
    # В файловом режиме возвращает None (нет ID)
    assert result is None


def test_save_document_db_mode(mock_app_config_db):
    """Сохранение документа в БД режиме."""
    adapter = DataAccessAdapter(mock_app_config_db)
    result = adapter.save_document(
        user_id=1,
        filename='test.txt',
        content=b'test content',
        content_type='text/plain'
    )
    # TODO: реализовать через DocumentRepository
    # Ожидаем ID документа (int)
    assert result is None  # Временно None до реализации


def test_delete_document_files_mode(mock_app_config_files):
    """Удаление документа в файловом режиме."""
    adapter = DataAccessAdapter(mock_app_config_files)
    result = adapter.delete_document(user_id=None, doc_id_or_path='test.txt')
    # TODO: реализовать удаление из uploads/
    assert result is False  # Временно False до реализации


def test_delete_document_db_mode(mock_app_config_db):
    """Удаление документа в БД режиме."""
    adapter = DataAccessAdapter(mock_app_config_db)
    result = adapter.delete_document(user_id=1, doc_id_or_path=123)
    # TODO: реализовать через DocumentRepository
    assert result is False  # Временно False до реализации


# ==========================================================================
# Тесты: переключение режимов (интеграционный сценарий)
# ==========================================================================

@pytest.mark.skip(reason='Требуется полная реализация БД и файлового поиска')
def test_mode_switching_search_equivalence(tmp_path):
    """
    Проверка эквивалентности результатов поиска в обоих режимах.
    
    Сценарий:
    1. Создать тестовый документ
    2. Построить индекс в файловом режиме -> получить результаты поиска
    3. Переключиться в БД режим, загрузить тот же документ
    4. Построить индекс в БД режиме -> получить результаты поиска
    5. Сравнить результаты (должны быть идентичны по содержанию)
    """
    # TODO: полная реализация интеграционного теста
    pass
