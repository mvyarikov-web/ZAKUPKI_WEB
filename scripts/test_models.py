#!/usr/bin/env python3
"""
Скрипт для тестирования всех моделей из models.json
Проверяет доступность и рекомендует оптимальные таймауты
"""
import json
import os
import sys
import time
from openai import OpenAI

# Путь к файлу моделей
MODELS_FILE = os.path.join(os.path.dirname(__file__), '..', 'index', 'models.json')

# Тестовый промпт
TEST_PROMPT = "Напиши краткое приветствие (1-2 предложения)."

def test_model(client, model_id, timeout=30):
    """
    Тестирует модель и возвращает время ответа или None при ошибке
    """
    try:
        start_time = time.time()
        
        # Проверяем, поддерживает ли модель system role (o-модели не поддерживают)
        supports_system = not model_id.startswith('o')
        
        if supports_system:
            messages = [
                {"role": "system", "content": "Ты помощник."},
                {"role": "user", "content": TEST_PROMPT}
            ]
        else:
            messages = [
                {"role": "user", "content": TEST_PROMPT}
            ]
        
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=100,
            timeout=timeout
        )
        
        elapsed = time.time() - start_time
        
        # Проверяем что получили ответ
        if response.choices and response.choices[0].message.content:
            return {
                'success': True,
                'elapsed': elapsed,
                'tokens': response.usage.total_tokens if response.usage else 0
            }
        else:
            return {'success': False, 'error': 'Пустой ответ'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def recommend_timeout(elapsed_time):
    """
    Рекомендует таймаут на основе времени ответа
    """
    if elapsed_time < 2:
        return 20  # Быстрая модель
    elif elapsed_time < 5:
        return 30  # Средняя модель
    elif elapsed_time < 10:
        return 45  # Медленная модель
    elif elapsed_time < 20:
        return 60  # Очень медленная модель (reasoning)
    else:
        return 90  # Экстремально медленная

def main():
    print("=" * 80)
    print("🧪 Тестирование моделей из models.json")
    print("=" * 80)
    
    # Загрузить API ключ из переменной окружения или config.py
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        # Попробовать загрузить из webapp/config.py
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from webapp.config import Config
            api_key = Config.OPENAI_API_KEY
        except Exception:
            pass
    
    if not api_key:
        print("❌ ОШИБКА: OPENAI_API_KEY не установлен")
        print("   Установите переменную окружения или добавьте в webapp/config.py")
        return False
    
    # Загрузить models.json
    if not os.path.exists(MODELS_FILE):
        print(f"❌ Файл {MODELS_FILE} не найден")
        return False
    
    with open(MODELS_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    models = config.get('models', [])
    if not models:
        print("❌ Модели не найдены в конфигурации")
        return False
    
    print(f"📊 Найдено моделей: {len(models)}")
    print()
    
    # Создать клиент OpenAI
    client = OpenAI(api_key=api_key)
    
    # Тестировать каждую модель
    results = []
    updates = []
    
    for i, model in enumerate(models, 1):
        model_id = model['model_id']
        current_timeout = model.get('timeout', 30)
        
        print(f"[{i}/{len(models)}] Тестирую {model_id}...")
        print(f"  Текущий таймаут: {current_timeout} сек")
        
        result = test_model(client, model_id, timeout=current_timeout)
        
        if result['success']:
            elapsed = result['elapsed']
            tokens = result['tokens']
            recommended_timeout = recommend_timeout(elapsed)
            
            print("  ✅ Успешно!")
            print(f"  ⏱️  Время ответа: {elapsed:.2f} сек")
            print(f"  🔢 Токены: {tokens}")
            print(f"  💡 Рекомендуемый таймаут: {recommended_timeout} сек")
            
            if recommended_timeout != current_timeout:
                print(f"  ⚠️  Рекомендуется изменить таймаут: {current_timeout} → {recommended_timeout}")
                updates.append({
                    'model_id': model_id,
                    'old_timeout': current_timeout,
                    'new_timeout': recommended_timeout
                })
                model['timeout'] = recommended_timeout
            
            results.append({
                'model_id': model_id,
                'status': 'OK',
                'elapsed': elapsed,
                'tokens': tokens,
                'timeout': recommended_timeout
            })
        else:
            error = result.get('error', 'Неизвестная ошибка')
            print(f"  ❌ ОШИБКА: {error}")
            
            # Проверяем, доступна ли модель вообще
            if 'does not exist' in error.lower() or 'model_not_found' in error.lower():
                print(f"  ⚠️  Модель {model_id} не существует в OpenAI API!")
                print("  💡 Рекомендуется удалить эту модель или заменить на актуальную")
            
            results.append({
                'model_id': model_id,
                'status': 'FAILED',
                'error': error
            })
        
        print()
    
    # Итоговая статистика
    print("=" * 80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    
    successful = sum(1 for r in results if r['status'] == 'OK')
    failed = sum(1 for r in results if r['status'] == 'FAILED')
    
    print(f"✅ Успешно: {successful}/{len(models)}")
    print(f"❌ Ошибки: {failed}/{len(models)}")
    print()
    
    if updates:
        print("🔄 РЕКОМЕНДУЕМЫЕ ОБНОВЛЕНИЯ ТАЙМАУТОВ:")
        for update in updates:
            print(f"  • {update['model_id']}: {update['old_timeout']} → {update['new_timeout']} сек")
        print()
        
        # Спросить пользователя
        response = input("Применить рекомендуемые таймауты? (y/n): ").lower().strip()
        if response == 'y':
            # Создать резервную копию
            backup_file = MODELS_FILE + '.backup'
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"💾 Резервная копия: {backup_file}")
            
            # Обновить models.json
            with open(MODELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Файл {MODELS_FILE} обновлен!")
        else:
            print("⏭️  Обновление пропущено")
    else:
        print("✅ Все таймауты оптимальны, обновление не требуется")
    
    return successful > 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
