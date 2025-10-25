"""
Тест проверки работы OpenAI API.
Отправляет простой запрос к GPT для проверки корректности API-ключа.
"""
import os
import sys
import pytest

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем .env перед импортом сервиса
def _load_env():
    """Загрузить переменные из .env."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[7:].strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value

_load_env()

from webapp.services.gpt_analysis import GPTAnalysisService


def test_openai_api_key_exists():
    """Проверка наличия API-ключа в окружении."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    assert api_key, "OPENAI_API_KEY не найден в переменных окружения"
    assert api_key.startswith('sk-'), "API-ключ имеет неверный формат (должен начинаться с 'sk-')"
    print(f"\n✓ API-ключ найден: {api_key[:10]}...")


def test_openai_api_connection():
    """Проверка подключения к OpenAI API и корректности ключа.
    
    Отправляет простой вопрос о дне недели.
    """
    # Пропускаем тест, если ключ не настроен
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        pytest.skip("OPENAI_API_KEY не настроен")
    
    service = GPTAnalysisService()
    
    # Проверяем, что сервис получил ключ
    assert service.api_key, "Сервис не смог получить API-ключ"
    print(f"\n✓ Сервис инициализирован с ключом: {service.api_key[:10]}...")
    
    # Отправляем тестовый запрос
    test_prompt = "Ответь одним словом на русском языке: какой сегодня день недели?"
    test_text = ""  # Пустой текст, только промпт
    
    print(f"\n→ Отправка тестового запроса к OpenAI API...")
    success, message, response = service.analyze_text(
        text=test_text,
        prompt=test_prompt,
        max_request_size=4096
    )
    
    # Проверяем результат
    if not success:
        # Если получили 429 (Too Many Requests) - это означает, что ключ валиден, но превышена квота
        if '429' in message or 'Too Many Requests' in message or 'quota' in message.lower():
            print(f"\n⚠️ API ключ валиден, но превышена квота запросов")
            print(f"  Сообщение: {message}")
            print(f"✓ Ключ настроен корректно (проверка пройдена)")
            pytest.skip("Превышена квота API, но ключ валиден")
        else:
            pytest.fail(f"Запрос к API не удался: {message}")
    
    assert response, "API вернул пустой ответ"
    
    print(f"\n✓ API ответил успешно!")
    print(f"  Вопрос: {test_prompt}")
    print(f"  Ответ: {response}")
    
    # Проверяем, что ответ содержит день недели (примерная проверка)
    days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    response_lower = response.lower()
    contains_day = any(day in response_lower for day in days)
    
    if contains_day:
        print(f"✓ Ответ содержит день недели")
    else:
        print(f"⚠️ Ответ не содержит явного дня недели, но запрос прошёл успешно")


@pytest.mark.skipif(
    not os.environ.get('OPENAI_API_KEY'),
    reason="OPENAI_API_KEY не настроен"
)
def test_openai_service_initialization():
    """Проверка правильной инициализации сервиса."""
    service = GPTAnalysisService()
    
    assert service.api_key, "API-ключ не загружен в сервис"
    assert service.api_url == "https://api.openai.com/v1/chat/completions", "Неверный URL API"
    assert service.model == "gpt-3.5-turbo", "Неверная модель по умолчанию"
    
    print(f"\n✓ Сервис инициализирован корректно")
    print(f"  URL: {service.api_url}")
    print(f"  Model: {service.model}")
    print(f"  Max tokens: {service.max_tokens}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
