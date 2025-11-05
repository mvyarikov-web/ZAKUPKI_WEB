#!/usr/bin/env python3
"""
Скрипт для тестирования валидации API ключей и отображения аналитики
"""

from utils.api_keys_manager_multiple import get_api_keys_manager_multiple

def test_validation():
    """Тестирование валидации ключей"""
    manager = get_api_keys_manager_multiple()
    
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ВАЛИДАЦИИ API КЛЮЧЕЙ")
    print("=" * 80)
    
    # Получаем список всех ключей
    keys_result = manager.list_all_keys()
    all_keys = keys_result.get('keys', [])
    
    for key_data in all_keys:
        provider = key_data['provider']
        provider_name = 'OpenAI' if provider == 'openai' else 'DeepSeek'
        print(f"\n{'='*80}")
        print(f"Провайдер: {provider_name}")
        print(f"Статус: {key_data.get('status', 'unknown')}")
        print(f"Основной: {key_data.get('is_primary', False)}")
        
        api_key = key_data.get('api_key')
        if api_key:
            masked_key = api_key[:5] + '***' + api_key[-4:] if len(api_key) > 10 else '***'
            print(f"Маскированный ключ: {masked_key}")
            print("\nПопытка валидации...")
            
            # Валидируем ключ
            success, result = manager.validate_key(provider, api_key)
            
            print("\nРезультат валидации:")
            print(f"  Успешно: {success}")
            
            if success:
                print(f"  Сообщение: {result.get('message')}")
                print(f"  Доступно моделей: {len(result.get('models', []))}")
                print(f"  Модели: {', '.join(result.get('models', []))}")
                
                if 'analytics' in result and result['analytics']:
                    print("\n  📊 АНАЛИТИКА:")
                    analytics = result['analytics']
                    for key, value in analytics.items():
                        print(f"    - {key}: {value}")
                
                if 'test_response' in result:
                    print(f"\n  Тестовый ответ: {result['test_response']}")
            else:
                print(f"  ❌ Ошибка: {result.get('error')}")
        else:
            print("\nКлюч не настроен")
    
    print("\n" + "=" * 80)
    print("ГОТОВО")
    print("=" * 80)

if __name__ == '__main__':
    test_validation()
