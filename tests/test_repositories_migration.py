"""
Тесты для репозиториев работы с AI моделями и состояниями файлов.
"""
import pytest
from datetime import datetime
from webapp.db.models import AIModelConfig, FileSearchState, User
from webapp.db.repositories.ai_model_config_repository import AIModelConfigRepository
from webapp.db.repositories.file_search_state_repository import FileSearchStateRepository


@pytest.fixture
def ai_model_config_repo(db_session):
    """Репозиторий для работы с конфигурацией AI моделей."""
    return AIModelConfigRepository(db_session)


@pytest.fixture
def file_search_state_repo(db_session):
    """Репозиторий для работы с состояниями файлов."""
    return FileSearchStateRepository(db_session)


@pytest.fixture
def test_user(db_session):
    """Тестовый пользователь."""
    user = User(
        email='test@example.com',
        password_hash='dummy_hash',
        role='user'
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestAIModelConfigRepository:
    """Тесты для AIModelConfigRepository."""
    
    def test_create_model_config(self, ai_model_config_repo, db_session):
        """Тест создания конфигурации модели."""
        data = {
            'display_name': 'Test Model',
            'provider': 'openai',
            'context_window_tokens': 4096,
            'price_input_per_1m': 150,  # центы
            'price_output_per_1m': 600,  # центы
            'is_enabled': True,
            'is_default': True
        }
        
        model = ai_model_config_repo.create_or_update('test-model', data)
        
        assert model.model_id == 'test-model'
        assert model.display_name == 'Test Model'
        assert model.provider == 'openai'
        assert model.price_input_per_1m == 150
        assert model.is_default is True
    
    def test_get_by_model_id(self, ai_model_config_repo, db_session):
        """Тест получения модели по ID."""
        data = {
            'display_name': 'GPT-4',
            'provider': 'openai',
            'is_enabled': True
        }
        ai_model_config_repo.create_or_update('gpt-4', data)
        
        model = ai_model_config_repo.get_by_model_id('gpt-4')
        
        assert model is not None
        assert model.model_id == 'gpt-4'
        assert model.display_name == 'GPT-4'
    
    def test_get_enabled_models(self, ai_model_config_repo, db_session):
        """Тест получения только включённых моделей."""
        ai_model_config_repo.create_or_update('model-1', {
            'display_name': 'Model 1',
            'provider': 'openai',
            'is_enabled': True
        })
        ai_model_config_repo.create_or_update('model-2', {
            'display_name': 'Model 2',
            'provider': 'openai',
            'is_enabled': False
        })
        
        enabled = ai_model_config_repo.get_enabled_models()
        
        assert len(enabled) == 1
        assert enabled[0].model_id == 'model-1'
    
    def test_set_default_model(self, ai_model_config_repo, db_session):
        """Тест установки модели по умолчанию."""
        ai_model_config_repo.create_or_update('model-1', {
            'display_name': 'Model 1',
            'provider': 'openai',
            'is_enabled': True,
            'is_default': True
        })
        ai_model_config_repo.create_or_update('model-2', {
            'display_name': 'Model 2',
            'provider': 'openai',
            'is_enabled': True
        })
        
        # Меняем default на model-2
        result = ai_model_config_repo.set_default_model('model-2')
        
        assert result is True
        
        model1 = ai_model_config_repo.get_by_model_id('model-1')
        model2 = ai_model_config_repo.get_by_model_id('model-2')
        
        assert model1.is_default is False
        assert model2.is_default is True
    
    def test_to_legacy_format(self, ai_model_config_repo, db_session):
        """Тест конвертации в legacy формат."""
        ai_model_config_repo.create_or_update('gpt-4o-mini', {
            'display_name': 'GPT-4o Mini',
            'provider': 'openai',
            'context_window_tokens': 128000,
            'price_input_per_1m': 15,  # центы
            'price_output_per_1m': 60,  # центы
            'is_enabled': True,
            'is_default': True
        })
        
        models = ai_model_config_repo.get_enabled_models()
        legacy = ai_model_config_repo.to_legacy_format(models)
        
        assert 'models' in legacy
        assert 'default_model' in legacy
        assert len(legacy['models']) == 1
        assert legacy['default_model'] == 'gpt-4o-mini'
        
        model_dict = legacy['models'][0]
        assert model_dict['model_id'] == 'gpt-4o-mini'
        assert model_dict['display_name'] == 'GPT-4o Mini'
        assert model_dict['price_input_per_1m'] == 0.15  # центы → доллары
        assert model_dict['price_output_per_1m'] == 0.60
    
    def test_from_legacy_format(self, ai_model_config_repo, db_session):
        """Тест импорта из legacy формата."""
        legacy_data = {
            'models': [
                {
                    'model_id': 'gpt-4',
                    'display_name': 'GPT-4',
                    'provider': 'openai',
                    'context_window_tokens': 8192,
                    'price_input_per_1m': 30.0,  # доллары
                    'price_output_per_1m': 60.0,
                    'enabled': True
                }
            ],
            'default_model': 'gpt-4'
        }
        
        ai_model_config_repo.from_legacy_format(legacy_data)
        
        model = ai_model_config_repo.get_by_model_id('gpt-4')
        
        assert model is not None
        assert model.price_input_per_1m == 3000  # доллары → центы
        assert model.price_output_per_1m == 6000
        assert model.is_default is True


class TestFileSearchStateRepository:
    """Тесты для FileSearchStateRepository."""
    
    def test_set_file_status(self, file_search_state_repo, test_user, db_session):
        """Тест установки статуса файла."""
        state = file_search_state_repo.set_file_status(
            user_id=test_user.id,
            file_path='test/file.txt',
            status='contains_keywords',
            result={'matches': 5}
        )
        
        assert state.user_id == test_user.id
        assert state.file_path == 'test/file.txt'
        assert state.status == 'contains_keywords'
        assert state.result_json == {'matches': 5}
    
    def test_get_by_user_and_file(self, file_search_state_repo, test_user, db_session):
        """Тест получения состояния по пользователю и файлу."""
        file_search_state_repo.set_file_status(
            user_id=test_user.id,
            file_path='test/file.txt',
            status='processing'
        )
        
        state = file_search_state_repo.get_by_user_and_file(
            test_user.id, 'test/file.txt'
        )
        
        assert state is not None
        assert state.status == 'processing'
    
    def test_get_user_states(self, file_search_state_repo, test_user, db_session):
        """Тест получения всех состояний пользователя."""
        file_search_state_repo.set_file_status(
            test_user.id, 'file1.txt', 'contains_keywords'
        )
        file_search_state_repo.set_file_status(
            test_user.id, 'file2.txt', 'no_keywords'
        )
        
        states = file_search_state_repo.get_user_states(test_user.id)
        
        assert len(states) == 2
        file_paths = {s.file_path for s in states}
        assert file_paths == {'file1.txt', 'file2.txt'}
    
    def test_update_existing_status(self, file_search_state_repo, test_user, db_session):
        """Тест обновления существующего состояния."""
        # Создаём начальное состояние
        file_search_state_repo.set_file_status(
            test_user.id, 'file.txt', 'processing'
        )
        
        # Обновляем статус
        updated = file_search_state_repo.set_file_status(
            test_user.id, 'file.txt', 'contains_keywords', result={'matches': 3}
        )
        
        assert updated.status == 'contains_keywords'
        assert updated.result_json == {'matches': 3}
        
        # Проверяем что запись одна
        states = file_search_state_repo.get_user_states(test_user.id)
        assert len(states) == 1
    
    def test_clear_user_states(self, file_search_state_repo, test_user, db_session):
        """Тест очистки всех состояний пользователя."""
        file_search_state_repo.set_file_status(test_user.id, 'file1.txt', 'processing')
        file_search_state_repo.set_file_status(test_user.id, 'file2.txt', 'processing')
        
        count = file_search_state_repo.clear_user_states(test_user.id)
        
        assert count == 2
        
        states = file_search_state_repo.get_user_states(test_user.id)
        assert len(states) == 0
    
    def test_search_terms(self, file_search_state_repo, test_user, db_session):
        """Тест работы с поисковыми терминами."""
        # Устанавливаем термины
        file_search_state_repo.set_file_status(
            test_user.id, 'file.txt', 'processing', 
            search_terms='keyword1, keyword2'
        )
        
        # Получаем последние термины
        terms = file_search_state_repo.get_last_search_terms(test_user.id)
        assert terms == 'keyword1, keyword2'
        
        # Обновляем термины для всех файлов
        file_search_state_repo.set_last_search_terms(test_user.id, 'new terms')
        
        terms = file_search_state_repo.get_last_search_terms(test_user.id)
        assert terms == 'new terms'
    
    def test_to_legacy_format(self, file_search_state_repo, test_user, db_session):
        """Тест конвертации в legacy формат."""
        file_search_state_repo.set_file_status(
            test_user.id, 'file1.txt', 'contains_keywords',
            result={'matches': 5},
            search_terms='test terms'
        )
        file_search_state_repo.set_file_status(
            test_user.id, 'file2.txt', 'no_keywords'
        )
        
        legacy = file_search_state_repo.to_legacy_format(test_user.id)
        
        assert 'file_status' in legacy
        assert 'last_search_terms' in legacy
        assert 'last_updated' in legacy
        
        assert len(legacy['file_status']) == 2
        assert legacy['file_status']['file1.txt']['status'] == 'contains_keywords'
        assert legacy['last_search_terms'] == 'test terms'
    
    def test_from_legacy_format(self, file_search_state_repo, test_user, db_session):
        """Тест импорта из legacy формата."""
        legacy_data = {
            'file_status': {
                'file1.txt': {
                    'status': 'contains_keywords',
                    'result': {'matches': 3}
                },
                'file2.txt': {
                    'status': 'no_keywords',
                    'result': {}
                }
            },
            'last_search_terms': 'import test',
            'last_updated': datetime.now().isoformat()
        }
        
        file_search_state_repo.from_legacy_format(test_user.id, legacy_data)
        
        states = file_search_state_repo.get_user_states(test_user.id)
        assert len(states) == 2
        
        terms = file_search_state_repo.get_last_search_terms(test_user.id)
        assert terms == 'import test'
