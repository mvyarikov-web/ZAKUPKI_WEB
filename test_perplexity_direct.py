#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Perplexity API
Использование: python test_perplexity_direct.py pplx-ваш-ключ
"""
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_perplexity_api(api_key: str):
    """Прямой тест Perplexity API"""
    from openai import OpenAI
    
    print(f"🔑 Тестирование ключа: {api_key[:8]}...{api_key[-4:]}")
    print(f"🌐 Подключение к: https://api.perplexity.ai")
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai"
        )
        
        # Список моделей для проверки (в порядке приоритета)
        # Согласно https://docs.perplexity.ai/getting-started/models
        models_to_test = [
            'llama-3.1-sonar-small-128k-chat',
            'llama-3.1-sonar-large-128k-chat',
            'llama-3.1-sonar-small-128k-online',
            'llama-3.1-sonar-large-128k-online',
            'llama-3.1-sonar-huge-128k-online'
        ]
        
        for model in models_to_test:
            print(f"\n📝 Попытка использовать модель: {model}")
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Say hi"}],
                    max_tokens=10
                )
                
                print(f"✅ Модель {model} работает!")
                print(f"📊 Ответ: {response.choices[0].message.content}")
                
                if hasattr(response, 'usage'):
                    print(f"🔢 Токены: {response.usage.total_tokens} (вход: {response.usage.prompt_tokens}, выход: {response.usage.completion_tokens})")
                
                return True, model
                
            except Exception as model_err:
                print(f"❌ Модель {model} не работает: {str(model_err)[:100]}")
                continue
        
        print("\n⚠️ Ни одна из тестовых моделей не сработала")
        return False, None
        
    except Exception as e:
        print(f"\n❌ Общая ошибка API: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python test_perplexity_direct.py pplx-ваш-ключ")
        sys.exit(1)
    
    api_key = sys.argv[1]
    
    if not api_key.startswith('pplx-'):
        print("⚠️ Предупреждение: ключ не начинается с 'pplx-'")
    
    success, working_model = test_perplexity_api(api_key)
    
    if success:
        print(f"\n✅ Успех! Рабочая модель: {working_model}")
        print(f"💡 Используйте эту модель в качестве test_model в конфигурации")
        sys.exit(0)
    else:
        print("\n❌ Тест не пройден")
        sys.exit(1)
