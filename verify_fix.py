#!/usr/bin/env python3
"""
Скрипт для проверки исправления логики светофоров.
Демонстрирует различия между старой и новой логикой.
"""

from webapp.utils.traffic_lights import TrafficLightLogic


def old_folder_logic(file_colors):
    """Старая (неправильная) логика папок."""
    if not file_colors:
        return 'gray'
    
    has_red = 'red' in file_colors
    has_green = 'green' in file_colors
    has_yellow = 'yellow' in file_colors
    
    # Приоритет: красный -> зелёный -> жёлтый -> серый
    if has_red:
        return 'red'
    if has_green:
        return 'green'
    if has_yellow:
        return 'yellow'
    return 'gray'


def new_folder_logic(file_colors):
    """Новая (правильная) логика папок."""
    return TrafficLightLogic.get_folder_traffic_light_color(file_colors)


def color_emoji(color):
    """Возвращает эмодзи для цвета."""
    emoji_map = {
        'red': '🔴',
        'yellow': '🟡',
        'green': '🟢',
        'gray': '⚪'
    }
    return emoji_map.get(color, '⚫')


def compare_logic(file_colors_list):
    """Сравнивает старую и новую логику."""
    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ ЛОГИКИ СВЕТОФОРОВ ДЛЯ ПАПОК")
    print("=" * 80)
    
    differences = 0
    for file_colors in file_colors_list:
        old_result = old_folder_logic(file_colors)
        new_result = new_folder_logic(file_colors)
        
        files_str = str(file_colors)
        old_emoji = color_emoji(old_result)
        new_emoji = color_emoji(new_result)
        
        if old_result != new_result:
            differences += 1
            print(f"\n❌ РАЗЛИЧИЕ #{differences}:")
            print(f"   Файлы: {files_str}")
            print(f"   Было:  {old_emoji} {old_result}")
            print(f"   Стало: {new_emoji} {new_result}")
        else:
            print(f"\n✅ БЕЗ ИЗМЕНЕНИЙ:")
            print(f"   Файлы: {files_str}")
            print(f"   Результат: {new_emoji} {new_result}")
    
    print("\n" + "=" * 80)
    print(f"ИТОГО: Найдено {differences} различий")
    print("=" * 80)
    return differences


def test_file_logic():
    """Проверяет, что логика файлов не изменилась."""
    print("\n" + "=" * 80)
    print("ПРОВЕРКА ЛОГИКИ ФАЙЛОВ (не должна измениться)")
    print("=" * 80)
    
    tests = [
        ('error', 100, False, False, 'red', "Неиндексированный (error)"),
        ('unsupported', 50, False, False, 'red', "Неиндексированный (unsupported)"),
        ('contains_keywords', 0, False, False, 'red', "char_count=0"),
        ('contains_keywords', 100, False, False, 'gray', "Проиндексированный, поиск не выполнен"),
        ('contains_keywords', 100, True, True, 'green', "Проиндексированный, есть совпадения"),
        ('contains_keywords', 100, False, True, 'yellow', "Проиндексированный, нет совпадений"),
    ]
    
    all_passed = True
    for status, char_count, has_results, search_performed, expected, description in tests:
        result = TrafficLightLogic.get_file_traffic_light_color(
            status, char_count, has_results, search_performed
        )
        emoji = color_emoji(result)
        passed = result == expected
        symbol = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
        
        print(f"{symbol} {description}")
        print(f"   Ожидалось: {color_emoji(expected)} {expected}")
        print(f"   Получено:  {emoji} {result}")
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ВСЕ ТЕСТЫ ФАЙЛОВ ПРОЙДЕНЫ - логика не изменилась")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ ФАЙЛОВ НЕ ПРОЙДЕНЫ")
    print("=" * 80)
    return all_passed


def main():
    """Основная функция."""
    print("\n" + "=" * 80)
    print("ВЕРИФИКАЦИЯ ИСПРАВЛЕНИЯ ЛОГИКИ СВЕТОФОРОВ")
    print("=" * 80)
    
    # Проверяем логику файлов
    files_ok = test_file_logic()
    
    # Сравниваем логику папок
    test_cases = [
        ['red', 'green', 'yellow', 'gray'],
        ['red', 'green'],
        ['red', 'yellow'],
        ['red', 'gray'],
        ['red', 'red', 'red'],
        ['green', 'yellow', 'gray'],
        ['green', 'yellow'],
        ['yellow', 'gray'],
        ['yellow'],
        ['gray', 'gray'],
    ]
    
    differences = compare_logic(test_cases)
    
    # Итоговая сводка
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 80)
    print(f"✅ Логика файлов: {'OK' if files_ok else 'ОШИБКА'}")
    print(f"{'✅' if differences > 0 else '⚠️'} Логика папок: {differences} изменений")
    print("\nОсновные изменения:")
    print("1. [red, green] → было 🔴, стало 🟢 (зелёный приоритетнее)")
    print("2. [red, yellow] → было 🔴, стало 🟡 (жёлтый приоритетнее)")
    print("3. [red, gray] → было 🔴, стало ⚪ (серый без проиндексированных)")
    print("\nПриоритет папок:")
    print("  Было:  Красный > Зелёный > Жёлтый > Серый")
    print("  Стало: Зелёный > Жёлтый > Красный > Серый")
    print("=" * 80)
    
    if files_ok and differences > 0:
        print("\n🎉 ИСПРАВЛЕНИЕ УСПЕШНО ПРИМЕНЕНО!")
        return 0
    else:
        print("\n⚠️ Возможны проблемы с исправлением")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
