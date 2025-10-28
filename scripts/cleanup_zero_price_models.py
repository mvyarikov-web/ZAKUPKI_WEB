#!/usr/bin/env python3
"""
Скрипт для удаления моделей с нулевой стоимостью из models.json
"""
import json
import os
import sys

# Путь к файлу моделей
MODELS_FILE = os.path.join(os.path.dirname(__file__), '..', 'index', 'models.json')

def cleanup_zero_price_models():
    """Удалить все модели с нулевой стоимостью (price_input_per_1m == 0 и price_output_per_1m == 0)"""
    
    if not os.path.exists(MODELS_FILE):
        print(f"❌ Файл {MODELS_FILE} не найден")
        return False
    
    # Загрузить текущую конфигурацию
    with open(MODELS_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    original_models = config.get('models', [])
    original_count = len(original_models)
    
    print(f"📊 Всего моделей: {original_count}")
    
    # Фильтровать модели - оставляем только те, у которых хотя бы одна цена не равна 0
    filtered_models = []
    removed_count = 0
    
    for model in original_models:
        price_in = model.get('price_input_per_1m', 0)
        price_out = model.get('price_output_per_1m', 0)
        
        # Оставляем модель, если хотя бы одна цена не равна 0
        if price_in != 0.0 or price_out != 0.0:
            filtered_models.append(model)
        else:
            removed_count += 1
            print(f"  ❌ Удаляю: {model.get('model_id')} (цены: вход={price_in}, выход={price_out})")
    
    # Проверка: должна остаться хотя бы одна модель
    if len(filtered_models) == 0:
        print("⚠️  ОШИБКА: Нельзя удалить все модели. Должна остаться хотя бы одна.")
        print("   Добавьте стоимость хотя бы для одной модели перед запуском скрипта.")
        return False
    
    if removed_count == 0:
        print("✅ Нет моделей с нулевой стоимостью. Очистка не требуется.")
        return True
    
    # Обновить конфигурацию
    config['models'] = filtered_models
    
    # Если default_model был удален, установить первую оставшуюся
    default_model = config.get('default_model')
    remaining_ids = {m['model_id'] for m in filtered_models}
    
    if default_model and default_model not in remaining_ids:
        new_default = filtered_models[0]['model_id']
        config['default_model'] = new_default
        print(f"⚠️  Default модель '{default_model}' была удалена. Новая default: '{new_default}'")
    
    # Создать резервную копию
    backup_file = MODELS_FILE + '.backup'
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"💾 Резервная копия сохранена: {backup_file}")
    
    # Сохранить обновленную конфигурацию
    with open(MODELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Успешно удалено моделей: {removed_count}")
    print(f"📊 Осталось моделей: {len(filtered_models)}")
    print(f"💾 Файл обновлен: {MODELS_FILE}")
    
    return True

if __name__ == '__main__':
    print("=" * 70)
    print("🧹 Очистка моделей с нулевой стоимостью")
    print("=" * 70)
    
    success = cleanup_zero_price_models()
    
    sys.exit(0 if success else 1)
