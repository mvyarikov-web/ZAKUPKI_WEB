import json
import types
import pytest
import os
import sys

# Добавляем корень проекта в sys.path
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeEmbeddings:
    def get_embedding(self, text):
        return [0.1, 0.2, 0.3]


class FakeDB:
    def __init__(self):
        self._docs = {}

    def get_document_by_path(self, path):
        # Возвращаем фиктивный документ с id
        return {"id": 1, "path": path}

    def search_similar_chunks(self, query_embedding, top_k, min_similarity, document_ids):
        # Возвращаем фиктивные чанки
        return [
            {"file_name": "doc1.txt", "similarity": 0.91, "content": "chunk1"},
            {"file_name": "doc2.txt", "similarity": 0.88, "content": "chunk2"},
        ]


class FakeResponse:
    def __init__(self, use_search: bool):
        self.usage = types.SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300)
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps({
            "summary": ["ok"],
            "equipment": [],
            "installation": {}
        })))]
        # Поле, указывающее, использовался ли поиск
        self.search_results = [
            {"url": "https://example.com", "title": "t"}
        ] if use_search else None


class FakeClient:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_request = None

    class _Chat:
        def __init__(self, outer):
            self._outer = outer

        class _Completions:
            def __init__(self, outer):
                self._outer = outer

            def create(self, **kwargs):
                # Сохраняем параметры запроса для проверки в тестах
                self._outer._outer.last_request = kwargs
                return self._outer._outer._response

        @property
        def completions(self):
            return FakeClient._Chat._Completions(self)

    @property
    def chat(self):
        return FakeClient._Chat(self)


@pytest.fixture()
def rag_service(monkeypatch):
    from webapp import create_app
    from webapp.services.rag_service import RAGService

    app = create_app('testing')
    with app.app_context():
        svc = RAGService(database_url="", api_key="test-key")
        # Подменяем зависимости
        svc.db_available = True
        svc.db = FakeDB()
        svc.embeddings_service = FakeEmbeddings()
        yield svc


def test_search_mode_removes_max_tokens_and_sets_suffix(rag_service, monkeypatch):
    from webapp.services import rag_service as rag_mod

    # Настраиваем фейковый клиент, который вернет search_results
    fake_resp = FakeResponse(use_search=True)
    fake_client = FakeClient(fake_resp)

    monkeypatch.setattr(rag_mod.RAGService, "_get_client_for_model", lambda self, model: fake_client)

    ok, msg, result = rag_service.search_and_analyze(
        query="test",
        file_paths=["a.txt"],
        model="sonar",
        top_k=2,
        max_output_tokens=123,  # должен быть проигнорирован в режиме поиска
        temperature=0.1,
        upload_folder="uploads",
        search_params={
            "search_recency_filter": "month",
            "max_results": 5
        }
    )

    assert ok, msg
    # Проверяем, что max_tokens НЕ передан
    assert "max_tokens" not in fake_client.last_request, f"Не ожидали max_tokens в запросе: {fake_client.last_request}"
    # Проверяем, что disable_search НЕ установлен
    assert "disable_search" not in fake_client.last_request
    # Проверяем суффикс модели и флаг
    assert result["search_used"] is True
    assert result["model"].endswith("+ Search"), result["model"]


def test_no_search_mode_sets_disable_and_limits_tokens(rag_service, monkeypatch):
    from webapp.services import rag_service as rag_mod

    fake_resp = FakeResponse(use_search=False)
    fake_client = FakeClient(fake_resp)
    monkeypatch.setattr(rag_mod.RAGService, "_get_client_for_model", lambda self, model: fake_client)

    ok, msg, result = rag_service.search_and_analyze(
        query="test",
        file_paths=["a.txt"],
        model="sonar",
        top_k=2,
        max_output_tokens=321,
        temperature=0.1,
        upload_folder="uploads",
        search_params=None
    )

    assert ok, msg
    # В режиме без поиска ожидаем, что limit установлен
    assert fake_client.last_request.get("max_tokens") == 321
    # И что поиск отключен
    assert fake_client.last_request.get("disable_search") is True
    # Без суффикса и search_used=False
    assert result["search_used"] is False
    assert result["model"] == "sonar"
