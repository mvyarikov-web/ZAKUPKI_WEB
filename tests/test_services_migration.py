"""
Тесты для сервисов работы с конфигурацией моделей и состояниями файлов.
"""
import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from webapp.services.ai_model_config_service import AIModelConfigService
from webapp.services.file_search_state_service import FileSearchStateService


class TestAIModelConfigService:
    """Тесты для AIModelConfigService."""
    
    @pytest.fixture
    def service(self):
        """Сервис с отключённой БД."""
        with patch.object(AIModelConfigService, '_should_use_database', return_value=False):
            return AIModelConfigService()
    
    @pytest.fixture
    def mock_models_config(self):
        """Мок конфигурации моделей."""
        return {
            'models': [
                {
                    'model_id': 'gpt-4o-mini',
                    'display_name': 'GPT-4o Mini',
                    'provider': 'openai',
                    'context_window_tokens': 128000,
                    'price_input_per_1m': 0.15,
                    'price_output_per_1m': 0.60,
                    'enabled': True,
                    'supports_system_role': True
                },
                {
                    'model_id': 'gpt-4',
                    'display_name': 'GPT-4',
                    'provider': 'openai',
                    'context_window_tokens': 8192,
                    'price_input_per_1m': 30.0,
                    'price_output_per_1m': 60.0,
                    'enabled': True,
                    'supports_system_role': True
                }
            ],
            'default_model': 'gpt-4o-mini'
        }
    
    def test_load_config_from_file(self, service, mock_models_config, tmp_path):
        """Тест загрузки конфигурации из файла."""
        # Создаём временный файл
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            config = service.load_config()
        
        assert 'models' in config
        assert 'default_model' in config
        assert len(config['models']) == 2
        assert config['default_model'] == 'gpt-4o-mini'
    
    def test_load_config_migrates_old_format(self, service, tmp_path):
        """Тест миграции старого формата (массив моделей)."""
        old_format = [
            {
                'model_id': 'gpt-4',
                'display_name': 'GPT-4',
                'price_input_per_1M': 30.0,  # старый ключ
                'price_output_per_1M': 60.0
            }
        ]
        
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(old_format))
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            config = service.load_config()
        
        assert isinstance(config, dict)
        assert 'models' in config
        assert 'default_model' in config
        assert config['models'][0]['price_input_per_1m'] == 30.0  # новый ключ
    
    def test_save_config_to_file(self, service, mock_models_config, tmp_path):
        """Тест сохранения конфигурации в файл."""
        config_file = tmp_path / "models.json"
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            service.save_config(mock_models_config)
        
        assert config_file.exists()
        
        with open(config_file, 'r') as f:
            saved_config = json.load(f)
        
        assert saved_config == mock_models_config
    
    def test_get_model_by_id(self, service, mock_models_config, tmp_path):
        """Тест получения модели по ID."""
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            model = service.get_model_by_id('gpt-4')
        
        assert model is not None
        assert model['model_id'] == 'gpt-4'
        assert model['display_name'] == 'GPT-4'
    
    def test_get_default_model(self, service, mock_models_config, tmp_path):
        """Тест получения модели по умолчанию."""
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            model = service.get_default_model()
        
        assert model is not None
        assert model['model_id'] == 'gpt-4o-mini'
    
    def test_set_default_model(self, service, mock_models_config, tmp_path):
        """Тест установки модели по умолчанию."""
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            result = service.set_default_model('gpt-4')
            assert result is True
            
            config = service.load_config()
            assert config['default_model'] == 'gpt-4'
    
    def test_add_models(self, service, mock_models_config, tmp_path):
        """Тест добавления новых моделей."""
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        new_models = [
            {
                'model_id': 'claude-3',
                'display_name': 'Claude 3',
                'provider': 'anthropic',
                'enabled': True
            }
        ]
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            service.add_models(new_models)
            
            config = service.load_config()
            assert len(config['models']) == 3
            
            claude = next(m for m in config['models'] if m['model_id'] == 'claude-3')
            assert claude['display_name'] == 'Claude 3'
    
    def test_update_existing_model(self, service, mock_models_config, tmp_path):
        """Тест обновления существующей модели."""
        config_file = tmp_path / "models.json"
        config_file.write_text(json.dumps(mock_models_config))
        
        updates = [
            {
                'model_id': 'gpt-4',
                'display_name': 'GPT-4 Turbo',  # обновляем название
                'context_window_tokens': 128000  # обновляем контекст
            }
        ]
        
        with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
            service.add_models(updates)
            
            model = service.get_model_by_id('gpt-4')
            assert model['display_name'] == 'GPT-4 Turbo'
            assert model['context_window_tokens'] == 128000


class TestFileSearchStateService:
    """Тесты для FileSearchStateService."""
    
    @pytest.fixture
    def service(self, tmp_path):
        """Сервис с файловым хранилищем."""
        state_file = tmp_path / "search_results.json"
        with patch.object(FileSearchStateService, '_should_use_database', return_value=False):
            return FileSearchStateService(str(state_file))
    
    def test_set_and_get_file_status(self, service):
        """Тест установки и получения статуса файла."""
        service.set_file_status('test/file.txt', 'contains_keywords', {'matches': 5})
        
        status = service.get_file_status('test/file.txt')
        
        assert status['status'] == 'contains_keywords'
        assert status['result']['matches'] == 5
    
    def test_get_all_statuses(self, service):
        """Тест получения всех статусов."""
        service.set_file_status('file1.txt', 'contains_keywords')
        service.set_file_status('file2.txt', 'no_keywords')
        
        all_statuses = service.get_file_status()
        
        assert len(all_statuses) == 2
        assert 'file1.txt' in all_statuses
        assert 'file2.txt' in all_statuses
    
    def test_update_file_statuses(self, service):
        """Тест пакетного обновления статусов."""
        statuses = {
            'file1.txt': {'status': 'contains_keywords', 'result': {'matches': 3}},
            'file2.txt': {'status': 'no_keywords', 'result': {}}
        }
        
        service.update_file_statuses(statuses)
        
        all_statuses = service.get_file_status()
        assert len(all_statuses) == 2
        assert all_statuses['file1.txt']['status'] == 'contains_keywords'
    
    def test_clear_statuses(self, service):
        """Тест очистки всех статусов."""
        service.set_file_status('file1.txt', 'processing')
        service.set_file_status('file2.txt', 'processing')
        
        service.clear()
        
        all_statuses = service.get_file_status()
        assert len(all_statuses) == 0
    
    def test_search_terms(self, service):
        """Тест работы с поисковыми терминами."""
        service.set_last_search_terms('keyword1, keyword2')
        
        terms = service.get_last_search_terms()
        assert terms == 'keyword1, keyword2'
    
    def test_get_all(self, service):
        """Тест получения полного состояния."""
        service.set_file_status('file.txt', 'processing')
        service.set_last_search_terms('test terms')
        
        all_data = service.get_all()
        
        assert 'file_status' in all_data
        assert 'last_search_terms' in all_data
        assert 'last_updated' in all_data
        assert all_data['last_search_terms'] == 'test terms'
    
    def test_file_locking(self, service):
        """Тест файловой блокировки при одновременной записи."""
        import threading
        import time
        
        def update_status(file_path, status):
            service.set_file_status(file_path, status)
            time.sleep(0.01)
        
        # Запускаем несколько потоков
        threads = []
        for i in range(5):
            t = threading.Thread(target=update_status, args=(f'file{i}.txt', 'processing'))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Проверяем, что все статусы записались
        all_statuses = service.get_file_status()
        assert len(all_statuses) == 5


class TestServiceIntegration:
    """Интеграционные тесты для сервисов."""
    
    def test_model_config_service_dual_mode(self, tmp_path):
        """Тест переключения между БД и файлом."""
        config_file = tmp_path / "models.json"
        mock_config = {
            'models': [
                {
                    'model_id': 'test-model',
                    'display_name': 'Test Model',
                    'provider': 'openai',
                    'enabled': True
                }
            ],
            'default_model': 'test-model'
        }
        config_file.write_text(json.dumps(mock_config))
        
        # Файловый режим
        with patch.object(AIModelConfigService, '_should_use_database', return_value=False):
            service = AIModelConfigService()
            with patch.object(service, '_get_legacy_path', return_value=str(config_file)):
                model = service.get_model_by_id('test-model')
                assert model is not None
    
    def test_file_state_service_persistence(self, tmp_path):
        """Тест сохранения состояния между созданиями сервиса."""
        state_file = tmp_path / "search_results.json"
        
        # Первый экземпляр сервиса
        with patch.object(FileSearchStateService, '_should_use_database', return_value=False):
            service1 = FileSearchStateService(str(state_file))
            service1.set_file_status('file.txt', 'contains_keywords')
        
        # Второй экземпляр сервиса читает то же состояние
        with patch.object(FileSearchStateService, '_should_use_database', return_value=False):
            service2 = FileSearchStateService(str(state_file))
            status = service2.get_file_status('file.txt')
            assert status['status'] == 'contains_keywords'
