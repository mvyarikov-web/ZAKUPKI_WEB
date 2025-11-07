"""Заглушка: тесты AI RAG моделей отключены (не входят в базовый набор).

Полная проверка перенесена в интеграционные тесты и ручные сценарии.
"""

import pytest

pytestmark = pytest.mark.skip("Пропущено: тяжёлый тест вне базового набора")


def test_models_placeholder():
    assert True
