import sys
import types
import json
from pathlib import Path


def test_provider_config_present():
    from utils.api_keys_manager_multiple import PROVIDERS
    assert 'perplexity' in PROVIDERS
    cfg = PROVIDERS['perplexity']
    assert cfg['base_url'] == 'https://api.perplexity.ai'
    assert cfg['test_model'].startswith('llama-3.1-sonar')


def test_models_json_has_perplexity():
    models_path = Path(__file__).resolve().parents[1] / 'index' / 'models.json'
    assert models_path.exists(), 'index/models.json отсутствует'
    data = json.loads(models_path.read_text('utf-8'))
    perpl = [m for m in data.get('models', []) if m.get('provider') == 'perplexity']
    assert len(perpl) >= 1, 'Нет моделей с провайдером perplexity в models.json'


def test_ui_has_perplexity_option():
    html_path = Path(__file__).resolve().parents[1] / 'templates' / 'api_keys_manager_new.html'
    txt = html_path.read_text('utf-8')
    assert 'option value="perplexity"' in txt or 'option value=\"perplexity\"' in txt


def test_ai_rag_get_client_uses_perplexity_base_url(monkeypatch):
    # Подменяем модуль openai на простой стаб
    fake_openai = types.SimpleNamespace()

    class FakeClient:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout

        # эмулируем интерфейс, хотя он не используется в тесте
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return None

    fake_openai.OpenAI = FakeClient
    monkeypatch.setitem(sys.modules, 'openai', fake_openai)

    # Подменяем загрузку конфигурации моделей
    import importlib
    ai_rag = importlib.import_module('webapp.routes.ai_rag')

    def fake_load_models_config():
        return {
            'models': [
                {
                    'model_id': 'llama-3.1-sonar-small-128k-chat',
                    'provider': 'perplexity',
                    'timeout': 30,
                    'supports_system_role': True
                }
            ],
            'default_model': 'llama-3.1-sonar-small-128k-chat'
        }

    monkeypatch.setattr(ai_rag, '_load_models_config', fake_load_models_config)

    client = ai_rag._get_api_client('llama-3.1-sonar-small-128k-chat', 'pplx-TESTKEY', timeout=45)
    assert isinstance(client, FakeClient)
    assert client.base_url == 'https://api.perplexity.ai'
    assert client.api_key == 'pplx-TESTKEY'
    assert client.timeout == 45


def test_rag_service_get_client_perplexity(monkeypatch):
    # Подменяем openai
    fake_openai = types.SimpleNamespace()

    class FakeClient:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout

    fake_openai.OpenAI = FakeClient
    monkeypatch.setitem(sys.modules, 'openai', fake_openai)

    # Подменяем менеджер ключей, чтобы не зависеть от файлов
    class FakeKeysMgr:
        def get_key(self, provider: str):
            return None

    def fake_get_mgr():
        return FakeKeysMgr()

    import importlib
    rag_service = importlib.import_module('webapp.services.rag_service')
    monkeypatch.setattr(rag_service, 'get_api_keys_manager_multiple', fake_get_mgr)

    svc = rag_service.RAGService(database_url='', api_key='pplx-KEY')
    client = svc._get_client_for_model('llama-3.1-sonar-small-128k-chat')
    assert isinstance(client, FakeClient)
    assert client.base_url == 'https://api.perplexity.ai'
    assert client.api_key == 'pplx-KEY'
