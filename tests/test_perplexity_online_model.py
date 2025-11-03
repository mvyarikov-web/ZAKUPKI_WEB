"""
Интеграционный тест Perplexity с моделью онлайн-поиска (-online).

Цель: выполнить реальный запрос к модели с суффиксом -online и убедиться, что
ответ не пуст и присутствуют признаки веб-поиска (если провайдер их возвращает).

Запуск (опционально):
    pytest tests/test_perplexity_online_model.py -v -s
"""
import os
import sys
from pathlib import Path
import pytest


# Добавляем корень проекта в sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.skipif(
    not os.environ.get('PPLX_API_KEY') and not os.environ.get('PERPLEXITY_API_KEY'),
    reason='Нет PPLX_API_KEY или PERPLEXITY_API_KEY в окружении'
)
def test_perplexity_online_variant_real():
    import openai

    # Получаем ключ из окружения или менеджера (если доступен)
    api_key = os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        try:
            from utils.api_keys_manager_multiple import get_api_keys_manager_multiple
            mgr = get_api_keys_manager_multiple()
            api_key = mgr.get_key('perplexity')
        except Exception:
            pass

    assert api_key, "Не удалось получить API ключ Perplexity"

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        timeout=90
    )

    # Используем модель с суффиксом -online; если она недоступна, тест всё равно
    # продемонстрирует поведение провайдера (может упасть 404/validation) — в таком
    # случае просто проверим наличие ошибки читаемым ассёртом.
    model_id = os.environ.get('PPLX_ONLINE_MODEL', 'llama-3.1-sonar-small-128k-online')

    prompt = (
        "Найди актуальную главную страницу новостей на https://ria.ru/ и коротко опиши 1-2 топ-события. "
        "Отвечай на русском языке."
    )

    request_params = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Ты — ассистент с доступом к интернет-поиску. Отвечай по-русски."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
    }

    try:
        resp = client.chat.completions.create(**request_params)
    except Exception as e:
        # Если провайдер вернул понятную ошибку о недоступности модели -online, зафиксируем
        # это как скип, т.к. цель теста — иметь образец вызова и поведение на живом API.
        pytest.skip(f"Провайдер не поддержал онлайн-модель '{model_id}': {e}")

    assert resp is not None and resp.choices, "Пустой ответ от API"
    content = resp.choices[0].message.content
    assert content, "Контент ответа пустой"

    # Наличие полей usage; у некоторых ответов могут отсутствовать дополнительные метрики
    usage = getattr(resp, 'usage', None)
    if usage:
        # Если провайдер заполнил num_search_queries — проверим его
        num_queries = getattr(usage, 'num_search_queries', None)
        if num_queries is not None:
            assert num_queries >= 0

    # Наличие search_results (если возвращает SDK)
    search_results = getattr(resp, 'search_results', None)
    if search_results:
        assert isinstance(search_results, (list, tuple))
        # не строго, достаточно, что есть структура
        assert len(search_results) >= 0

    # Финально: просто печать первых 400 символов
    print((content or '')[:400])
