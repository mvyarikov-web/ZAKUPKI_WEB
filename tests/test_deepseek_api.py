"""
Тесты для проверки подключения к DeepSeek API
"""
import pytest
import os
from openai import OpenAI


def test_deepseek_api_key_exists():
    """Проверка наличия API ключа DeepSeek в переменных окружения"""
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    assert api_key is not None, (
        "DEEPSEEK_API_KEY не найден в переменных окружения.\n"
        "Добавьте ключ в .env файл:\n"
        "DEEPSEEK_API_KEY=your_deepseek_api_key_here\n"
        "\nПолучить ключ можно на: https://platform.deepseek.com/api-keys"
    )
    assert len(api_key) > 10, "DEEPSEEK_API_KEY слишком короткий"


@pytest.mark.skipif(
    not os.environ.get('DEEPSEEK_API_KEY'),
    reason="DEEPSEEK_API_KEY не настроен"
)
def test_deepseek_chat_connection():
    """Тест базового подключения к deepseek-chat"""
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    
    # Создаём клиента DeepSeek
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    
    try:
        # Простой тестовый запрос
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Say 'Hello World' in Russian"}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        # Проверяем структуру ответа
        assert response is not None, "Ответ от API не получен"
        assert hasattr(response, 'choices'), "Ответ не содержит choices"
        assert len(response.choices) > 0, "Список choices пустой"
        assert hasattr(response.choices[0], 'message'), "Choice не содержит message"
        
        # Проверяем содержимое
        message_content = response.choices[0].message.content
        assert message_content is not None, "Содержимое сообщения пустое"
        assert len(message_content) > 0, "Содержимое сообщения имеет нулевую длину"
        
        # Проверяем usage (использование токенов)
        assert hasattr(response, 'usage'), "Ответ не содержит информацию об usage"
        assert response.usage.total_tokens > 0, "Количество токенов должно быть больше 0"
        
        print("\n✅ DeepSeek Chat успешно подключен!")
        print(f"   Ответ: {message_content[:100]}")
        print(f"   Токены: {response.usage.total_tokens}")
        
    except Exception as e:
        pytest.fail(f"Ошибка подключения к DeepSeek Chat: {str(e)}")


@pytest.mark.skipif(
    not os.environ.get('DEEPSEEK_API_KEY'),
    reason="DEEPSEEK_API_KEY не настроен"
)
def test_deepseek_reasoner_connection():
    """Тест базового подключения к deepseek-reasoner (режим размышлений)"""
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    
    # Создаём клиента DeepSeek
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    
    try:
        # Простой тестовый запрос с логической задачей
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "What is 2+2?"}
            ],
            max_tokens=100,
            temperature=0.3
        )
        
        # Проверяем структуру ответа
        assert response is not None, "Ответ от API не получен"
        assert hasattr(response, 'choices'), "Ответ не содержит choices"
        assert len(response.choices) > 0, "Список choices пустой"
        assert hasattr(response.choices[0], 'message'), "Choice не содержит message"
        
        # Проверяем содержимое (для reasoner может быть в reasoning_content)
        message = response.choices[0].message
        message_content = message.content or ""
        reasoning_content = getattr(message, 'reasoning_content', None) or ""
        
        # Хотя бы одно из полей должно быть заполнено
        assert (message_content or reasoning_content), "Оба поля (content и reasoning_content) пустые"
        
        # Проверяем usage (использование токенов)
        assert hasattr(response, 'usage'), "Ответ не содержит информацию об usage"
        assert response.usage.total_tokens > 0, "Количество токенов должно быть больше 0"
        
        print("\n✅ DeepSeek Reasoner успешно подключен!")
        if message_content:
            print(f"   Ответ: {message_content[:100]}")
        if reasoning_content:
            print(f"   Рассуждение: {reasoning_content[:100]}")
        print(f"   Токены: {response.usage.total_tokens}")
        
    except Exception as e:
        pytest.fail(f"Ошибка подключения к DeepSeek Reasoner: {str(e)}")


@pytest.mark.skipif(
    not os.environ.get('DEEPSEEK_API_KEY'),
    reason="DEEPSEEK_API_KEY не настроен"
)
def test_deepseek_token_counting():
    """Тест подсчёта токенов для DeepSeek моделей"""
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    
    test_message = "This is a test message for token counting."
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": test_message}
            ],
            max_tokens=10
        )
        
        # Проверяем, что токены подсчитаны корректно
        usage = response.usage
        assert usage.prompt_tokens > 0, "Входные токены не подсчитаны"
        assert usage.completion_tokens > 0, "Выходные токены не подсчитаны"
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens, \
            "Общее количество токенов не соответствует сумме входных и выходных"
        
        print("\n✅ Подсчёт токенов работает корректно!")
        print(f"   Входные: {usage.prompt_tokens}")
        print(f"   Выходные: {usage.completion_tokens}")
        print(f"   Всего: {usage.total_tokens}")
        
    except Exception as e:
        pytest.fail(f"Ошибка при подсчёте токенов: {str(e)}")


def test_deepseek_models_in_config():
    """Проверка наличия моделей DeepSeek в конфигурации"""
    import json
    from pathlib import Path
    
    # Путь к models.json
    models_file = Path(__file__).parent.parent / 'index' / 'models.json'
    
    assert models_file.exists(), f"Файл models.json не найден: {models_file}"
    
    with open(models_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    models = config.get('models', [])
    model_ids = [m['model_id'] for m in models]
    
    # Проверяем наличие DeepSeek моделей
    assert 'deepseek-chat' in model_ids, "deepseek-chat отсутствует в models.json"
    assert 'deepseek-reasoner' in model_ids, "deepseek-reasoner отсутствует в models.json"
    
    # Проверяем параметры моделей
    for model in models:
        if model['model_id'].startswith('deepseek-'):
            assert 'display_name' in model, f"{model['model_id']}: отсутствует display_name"
            assert 'description' in model, f"{model['model_id']}: отсутствует description"
            assert 'price_input_per_1m' in model, f"{model['model_id']}: отсутствует price_input_per_1m"
            assert 'price_output_per_1m' in model, f"{model['model_id']}: отсутствует price_output_per_1m"
            assert model.get('provider') == 'deepseek', f"{model['model_id']}: provider должен быть 'deepseek'"
            assert model.get('base_url') == 'https://api.deepseek.com', \
                f"{model['model_id']}: base_url должен быть 'https://api.deepseek.com'"
    
    print("\n✅ Модели DeepSeek корректно настроены в models.json")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
