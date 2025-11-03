"""
Тест для сравнения Perplexity Sonar и Sonar Pro.

Цель: повторить точные параметры запросов из программы и сравнить ответы.
"""
import pytest
import os
from openai import OpenAI


def _has_perplexity_key() -> bool:
    """Проверка наличия API ключа Perplexity."""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.api_keys_manager_multiple import APIKeysManagerMultiple
        manager = APIKeysManagerMultiple()
        key = manager.get_key('perplexity')
        return bool(key and len(key) > 10)
    except Exception as e:
        print(f"❌ Exception in _has_perplexity_key: {e}")
        return False


@pytest.mark.skipif(not _has_perplexity_key(), reason="Perplexity API key not found")
def test_sonar_pro_with_exact_params():
    """
    Тест Sonar Pro с точными параметрами из логов (11:28:41).
    Ожидается: корректный ответ с анекдотами.
    """
    from utils.api_keys_manager_multiple import APIKeysManagerMultiple
    
    manager = APIKeysManagerMultiple()
    api_key = manager.get_key('perplexity')
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )
    
    # Точные параметры из рабочего запроса
    messages = [
        {
            "role": "system",
            "content": "Вы - помощник для анализа документов. Отвечайте на русском языке. Если доступен веб‑поиск, сначала выполни поиск в интернете по запросу и приведи ссылки на источники. Игнорируй загруженные документы и основывайся на запросе пользователя и результатах веб‑поиска."
        },
        {
            "role": "user",
            "content": "Запрос: Зайди на сайт https://www.anekdot.ru/, найди вкладку с анекдотами за вчера, верни все анекдоты с этой страницы, проанализируй, есть ли анекдоты про психологию, если есть верни их в отдельном блоке (анекдоты про психологию) - Дай прямую ссылку на страницу, с которой будешь брать анекдоты. Не давай общую справку о сайте. Если не найдено — напиши, что не найдено»."
        }
    ]
    
    response = client.chat.completions.create(
        model="sonar-pro",
        messages=messages,
        temperature=0.3,
        extra_body={
            "enable_search_classifier": True,
            "search_mode": "web",
            "language_preference": "ru",
            "web_search_options": {
                "search_context_size": "medium"
            },
            "max_results": 5,
            "search_domain_filter": ["www.anekdot.ru"],
            "search_after_date_filter": "11/01/2025",
            "search_before_date_filter": "11/02/2025",
            "country": "RU"
        }
    )
    
    answer = response.choices[0].message.content
    
    # Проверки
    print(f"\n{'='*80}")
    print(f"SONAR PRO ОТВЕТ (длина: {len(answer)} символов)")
    print(f"{'='*80}")
    print(answer[:800])
    if len(answer) > 800:
        print(f"\n... (еще {len(answer) - 800} символов)")
    print(f"{'='*80}\n")
    
    # Проверяем, что ответ не содержит отказа
    refusal_phrases = [
        "не могу напрямую заходить",
        "не могу зайти на",
        "не могу просматривать",
        "не могу получить доступ",
        "не найдено"
    ]
    
    answer_lower = answer.lower()
    found_refusals = [phrase for phrase in refusal_phrases if phrase in answer_lower]
    
    assert len(answer) > 200, f"Ответ слишком короткий: {len(answer)} символов"
    assert not found_refusals, f"Найдены фразы отказа: {found_refusals}"
    
    # Проверяем наличие положительных индикаторов
    positive_indicators = ["анекдот", "https://www.anekdot.ru"]
    found_indicators = [ind for ind in positive_indicators if ind.lower() in answer_lower]
    
    assert len(found_indicators) >= 1, f"Не найдены положительные индикаторы: {positive_indicators}"
    
    print(f"✅ SONAR PRO: Успешно вернул анекдоты ({len(answer)} символов)")
    print(f"   Найдены индикаторы: {found_indicators}")


@pytest.mark.skipif(not _has_perplexity_key(), reason="Perplexity API key not found")
def test_sonar_with_exact_params():
    """
    Тест обычного Sonar с параметрами из логов (11:43:54).
    Проверяем, работает ли с теми же параметрами, что у Sonar Pro.
    """
    from utils.api_keys_manager_multiple import APIKeysManagerMultiple
    
    manager = APIKeysManagerMultiple()
    api_key = manager.get_key('perplexity')
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )
    
    # Используем ТЕ ЖЕ параметры, что у Sonar Pro (для честного сравнения)
    messages = [
        {
            "role": "system",
            "content": "Вы - помощник для анализа документов. Отвечайте на русском языке. Если доступен веб‑поиск, сначала выполни поиск в интернете по запросу и приведи ссылки на источники. Игнорируй загруженные документы и основывайся на запросе пользователя и результатах веб‑поиска."
        },
        {
            "role": "user",
            "content": "Запрос: Зайди на сайт https://www.anekdot.ru/, найди вкладку с анекдотами за вчера, верни все анекдоты с этой страницы, проанализируй, есть ли анекдоты про психологию, если есть верни их в отдельном блоке (анекдоты про психологию) - Дай прямую ссылку на страницу, с которой будешь брать анекдоты. Не давай общую справку о сайте. Если не найдено — напиши, что не найдено»."
        }
    ]
    
    response = client.chat.completions.create(
        model="sonar",  # <-- обычный Sonar
        messages=messages,
        temperature=0.3,
        extra_body={
            "enable_search_classifier": True,
            "search_mode": "web",
            "language_preference": "ru",
            "web_search_options": {
                "search_context_size": "medium"  # <-- MEDIUM, как у Pro
            },
            "max_results": 5,
            "search_domain_filter": ["www.anekdot.ru"],  # <-- с www
            "search_after_date_filter": "11/01/2025",
            "search_before_date_filter": "11/02/2025",
            "country": "RU"
        }
    )
    
    answer = response.choices[0].message.content
    
    # Проверки
    print(f"\n{'='*80}")
    print(f"SONAR ОТВЕТ (длина: {len(answer)} символов)")
    print(f"{'='*80}")
    print(answer[:800])
    if len(answer) > 800:
        print(f"\n... (еще {len(answer) - 800} символов)")
    print(f"{'='*80}\n")
    
    # Проверяем, что ответ не содержит отказа
    refusal_phrases = [
        "не могу напрямую заходить",
        "не могу зайти на",
        "не могу просматривать",
        "не могу получить доступ"
    ]
    
    answer_lower = answer.lower()
    found_refusals = [phrase for phrase in refusal_phrases if phrase in answer_lower]
    
    # Для обычного Sonar допускаем отказ, но логируем
    if found_refusals:
        print(f"⚠️ SONAR: Найдены фразы отказа: {found_refusals}")
        print(f"   Возможно, обычный Sonar требует других параметров")
    else:
        print(f"✅ SONAR: Успешно вернул анекдоты ({len(answer)} символов)")
        
        # Проверяем наличие положительных индикаторов
        positive_indicators = ["анекдот", "https://www.anekdot.ru"]
        found_indicators = [ind for ind in positive_indicators if ind.lower() in answer_lower]
        print(f"   Найдены индикаторы: {found_indicators}")
    
    assert len(answer) > 100, f"Ответ слишком короткий: {len(answer)} символов"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
