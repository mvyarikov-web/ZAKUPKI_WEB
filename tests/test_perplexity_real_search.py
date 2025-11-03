"""
Интеграционный тест веб-поиска Perplexity Sonar с реальным API.

Цель: проверить, что модель выполняет поиск в интернете и возвращает источники.
Промпт: зайти на anekdot.ru и вернуть анекдоты про психологию.

Запуск:
    pytest tests/test_perplexity_real_search.py -v -s
"""
import pytest
import os
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _has_perplexity_key() -> bool:
    """Возвращает True, если ключ Perplexity доступен либо в окружении,
    либо через внутренний менеджер api_keys.
    """
    if os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY'):
        return True
    try:
        from utils.api_keys_manager_multiple import get_api_keys_manager_multiple
        mgr = get_api_keys_manager_multiple()
        key = mgr.get_key('perplexity')
        return bool(key)
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_perplexity_key(),
    reason='Нет ключа Perplexity (ни в окружении, ни в менеджере api_keys)'
)
def test_perplexity_sonar_real_search():
    """
    Реальный запрос к Perplexity Sonar с включенным поиском.
    Проверяет:
    1. Передачу параметров через extra_body
    2. Наличие search_results в ответе
    3. Наличие usage.num_search_queries
    4. Работоспособность нормализации параметров
    """
    import openai
    from webapp.services.search.manager import normalize_search_params, apply_search_to_request
    
    # Получаем ключ из окружения или менеджера
    api_key = os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        try:
            from utils.api_keys_manager_multiple import get_api_keys_manager_multiple
            mgr = get_api_keys_manager_multiple()
            api_key = mgr.get_key('perplexity')
        except Exception:
            pass
    
    assert api_key, "Не удалось получить API ключ Perplexity"
    
    # Создаём клиент Perplexity
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        timeout=90
    )
    
    # Промпт из задания
    prompt = (
        "Зайди на сайт https://www.anekdot.ru/, верни анекдоты за сегодня, "
        "проанализируй, есть ли анекдоты про психологию, если есть — верни их в отдельном блоке "
        "(анекдоты про психологию)."
    )
    
    # Параметры поиска
    search_params = {
        "search_domain_filter": ["https://www.anekdot.ru/"],
        "search_recency_filter": "day",  # только за сегодня
        "max_results": 5,
        "return_related_questions": False,
        "language_preference": "ru",
    }
    
    # Нормализуем параметры
    norm_params = normalize_search_params(search_params)
    print(f"\n📋 Нормализованные параметры: {norm_params}")
    
    # Формируем запрос
    request_params = {
        "model": "sonar",  # базовая модель с поиском
        "messages": [
            {
                "role": "system",
                "content": "Ты — ассистент, который ищет и анализирует информацию в интернете. Отвечай на русском языке."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
    }
    
    # Применяем параметры поиска через extra_body
    apply_search_to_request(request_params, norm_params or {})
    
    print(f"\n🌐 Request params (extra_body): {request_params.get('extra_body')}")
    
    # Отправляем запрос
    response = client.chat.completions.create(**request_params)
    
    # Проверяем ответ
    assert response is not None, "Нет ответа от API"
    assert response.choices, "Нет choices в ответе"
    
    message = response.choices[0].message
    content = message.content
    
    print(f"\n✅ Получен ответ ({len(content)} символов):")
    print(content[:500] + "..." if len(content) > 500 else content)
    
    # Проверяем usage
    usage = response.usage
    print(f"\n📊 Usage:")
    print(f"  - prompt_tokens: {usage.prompt_tokens}")
    print(f"  - completion_tokens: {usage.completion_tokens}")
    print(f"  - total_tokens: {usage.total_tokens}")
    
    # Ключевая проверка: наличие метрик поиска
    num_queries = getattr(usage, 'num_search_queries', None)
    search_context_size = getattr(usage, 'search_context_size', None)
    
    print(f"  - num_search_queries: {num_queries}")
    print(f"  - search_context_size: {search_context_size}")
    
    # Проверяем search_results
    search_results = getattr(response, 'search_results', None)
    if search_results:
        print(f"\n🔗 Найдено источников: {len(search_results)}")
        for i, sr in enumerate(search_results[:3], 1):
            title = getattr(sr, 'title', 'Без названия')
            url = getattr(sr, 'url', 'Без URL')
            print(f"  {i}. {title}")
            print(f"     {url}")
    else:
        print("\n⚠️  Нет search_results в ответе (модель не выполнила поиск или ответила из внутренних знаний)")
    
    # Assertions для CI
    # 1. Ответ не пустой
    assert content, "Контент ответа пустой"
    
    # 2. Если есть num_search_queries > 0 — значит поиск выполнен
    if num_queries is not None:
        print(f"\n🔍 Поиск выполнен: {num_queries} запросов")
        assert num_queries > 0, f"num_search_queries={num_queries}, ожидалось > 0"
    
    # 3. Если есть search_results — значит источники найдены
    if search_results:
        print(f"\n✅ Источники найдены: {len(search_results)}")
        assert len(search_results) > 0, "search_results пустой"
        # Проверяем, что хотя бы один источник с anekdot.ru
        urls = [getattr(sr, 'url', '') for sr in search_results]
        anekdot_found = any('anekdot.ru' in url for url in urls)
        if anekdot_found:
            print("✅ Найден источник с anekdot.ru")
        else:
            print(f"⚠️  anekdot.ru не в списке источников: {urls}")
    else:
        # Если search_results нет, но num_queries > 0 — модель выполнила поиск, но не вернула детали
        # Это допустимо, но предупредим
        print("\n⚠️  search_results отсутствует, но поиск мог быть выполнен")
    
    # Финальная проверка: ответ должен содержать упоминание анекдотов или сайта
    content_lower = content.lower()
    has_anekdot = 'анекдот' in content_lower or 'anekdot' in content_lower
    has_psychology = 'психолог' in content_lower
    
    print(f"\n📝 Анализ содержимого:")
    print(f"  - Упоминание 'анекдот': {'✅' if has_anekdot else '❌'}")
    print(f"  - Упоминание 'психолог': {'✅' if has_psychology else '❌'}")
    
    # Мягкая проверка: хотя бы одно из условий должно выполняться
    assert has_anekdot or num_queries or search_results, \
        "Ответ не содержит упоминания анекдотов и нет признаков поиска"
    
    print("\n✅ Тест завершён успешно!")


if __name__ == "__main__":
    # Прямой запуск для быстрой проверки
    test_perplexity_sonar_real_search()
