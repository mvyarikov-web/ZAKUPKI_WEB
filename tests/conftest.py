"""Глобальные фикстуры для тестов Flask-приложения."""
from __future__ import annotations

from typing import Any, Callable, Dict

import pytest

from webapp import create_app


@pytest.fixture(scope="session")
def app():
    """Создаёт Flask-приложение в тестовом режиме и держит контекст приложения."""
    flask_app = create_app("testing")
    flask_app.config.update({
        "TESTING": True,
        "PRESERVE_CONTEXT_ON_EXCEPTION": False,
    })

    ctx = flask_app.app_context()
    ctx.push()
    try:
        yield flask_app
    finally:
        ctx.pop()


@pytest.fixture()
def auth_client(app):
    """Возвращает тестовый клиент с предустановленными заголовками авторизации."""
    client = app.test_client()
    default_headers: Dict[str, str] = {"X-User-ID": "1"}

    class _AuthClient:
        """Обёртка над Flask test_client с автоматическим добавлением заголовков."""

        def __init__(self, inner_client, base_headers: Dict[str, str]):
            self._inner = inner_client
            self._base_headers = base_headers

        def _merge_headers(self, headers: Dict[str, str] | None) -> Dict[str, str]:
            merged = dict(self._base_headers)
            if headers:
                merged.update(headers)
            return merged

        def _wrap(self, method: Callable[..., Any], *args: Any, **kwargs: Any):
            headers = kwargs.pop("headers", None)
            kwargs["headers"] = self._merge_headers(headers)
            return method(*args, **kwargs)

        def get(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.get, *args, **kwargs)

        def post(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.post, *args, **kwargs)

        def put(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.put, *args, **kwargs)

        def delete(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.delete, *args, **kwargs)

        def patch(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.patch, *args, **kwargs)

        def options(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.options, *args, **kwargs)

        def head(self, *args: Any, **kwargs: Any):
            return self._wrap(self._inner.head, *args, **kwargs)

        def __getattr__(self, item: str):
            return getattr(self._inner, item)

    return _AuthClient(client, default_headers)
