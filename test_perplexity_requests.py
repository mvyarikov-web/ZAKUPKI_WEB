#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Perplexity API через requests
Использование: python test_perplexity_requests.py pplx-ваш-ключ
"""
import sys
import requests
import json

def test_perplexity_api(api_key: str):
    """Прямой тест Perplexity API через requests"""
    
    print(f"🔑 Тестирование ключа: {api_key[:8]}...{api_key[-4:]}")
    print(f"🌐 Подключение к: https://api.perplexity.ai")
    
    url = "https://api.perplexity.ai/chat/completions"
    
    # Канонические модели согласно https://docs.perplexity.ai/getting-started/models
    models_to_test = [
        'sonar',                    # Быстрый, экономичный
        'sonar-pro',                # Продвинутый веб-поиск
        'sonar-reasoning',          # Рассуждение + поиск
        'sonar-reasoning-pro',      # Топ-уровень reasoning
        'sonar-deep-research'       # Длинные исследования
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for model in models_to_test:
        print(f"\n📝 Попытка использовать модель: {model}")
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Say hi"
                }
            ],
            "max_tokens": 10
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            print(f"📊 HTTP статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Модель {model} работает!")
                print(f"📝 Ответ: {data['choices'][0]['message']['content']}")
                
                if 'usage' in data:
                    usage = data['usage']
                    print(f"🔢 Токены: {usage['total_tokens']} (вход: {usage['prompt_tokens']}, выход: {usage['completion_tokens']})")
                
                return True, model
            else:
                print(f"❌ Ошибка: {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Исключение: {str(e)[:100]}")
            continue
    
    print("\n⚠️ Ни одна из тестовых моделей не сработала")
    return False, None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python test_perplexity_requests.py pplx-ваш-ключ")
        sys.exit(1)
    
    api_key = sys.argv[1]
    success, working_model = test_perplexity_api(api_key)
    
    if success:
        print(f"\n✅ Тест пройден! Рабочая модель: {working_model}")
        sys.exit(0)
    else:
        print("\n❌ Тест не пройден")
        sys.exit(1)
