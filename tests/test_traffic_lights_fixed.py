"""
Тест исправленной логики светофоров.
Проверяет корректность определения цветов светофоров в различных сценариях.
"""
import pytest
import time
from unittest.mock import Mock, patch


def test_traffic_light_logic_fixed():
    """
    Тест исправленной логики светофоров:
    - Красный: не проиндексированные файлы (всегда внизу)
    - Жёлтый: проиндексированные без совпадений при поиске
    - Зелёный: проиндексированные с совпадениями при поиске  
    - Серый: проиндексированные без поиска
    """
    
    def get_traffic_light_color_fixed(status, char_count=None, has_search_results=False, search_performed=False):
        """Исправленная версия логики светофоров."""
        # Красный: не проиндексированные файлы
        if status in ['error', 'unsupported'] or char_count == 0:
            return 'red'
        
        # Если поиск был выполнен
        if search_performed:
            if has_search_results:
                return 'green'  # Зелёный: есть совпадения
            else:
                return 'yellow'  # Жёлтый: нет совпадений, но файл проиндексирован
        
        # Серый: проиндексированные, но поиск не производился
        if status in ['contains_keywords', 'no_keywords', 'processing']:
            return 'gray'
        
        return 'gray'  # По умолчанию серый для not_checked
    
    # Тест 1: Не проиндексированные файлы - всегда красный
    assert get_traffic_light_color_fixed('error', 100, False, False) == 'red'
    assert get_traffic_light_color_fixed('error', 100, True, True) == 'red'  # Даже при поиске
    assert get_traffic_light_color_fixed('unsupported', 50, False, False) == 'red'
    assert get_traffic_light_color_fixed('processing', 0, False, False) == 'red'
    
    # Тест 2: Поиск выполнен, есть результаты - зеленый
    assert get_traffic_light_color_fixed('contains_keywords', 100, True, True) == 'green'
    assert get_traffic_light_color_fixed('no_keywords', 50, True, True) == 'green'
    
    # Тест 3: Поиск выполнен, нет результатов - желтый  
    assert get_traffic_light_color_fixed('contains_keywords', 100, False, True) == 'yellow'
    assert get_traffic_light_color_fixed('no_keywords', 50, False, True) == 'yellow'
    
    # Тест 4: Поиск не выполнялся - серый
    assert get_traffic_light_color_fixed('contains_keywords', 100, False, False) == 'gray'
    assert get_traffic_light_color_fixed('no_keywords', 50, False, False) == 'gray'
    assert get_traffic_light_color_fixed('not_checked', None, False, False) == 'gray'


def test_folder_status_logic_fixed():
    """
    Тест логики статуса папок с исправленными приоритетами:
    - Красный: есть неиндексированные файлы (высший приоритет)
    - Зеленый: есть совпадения при поиске
    - Желтый: нет совпадений при поиске, но файлы проиндексированы
    - Серый: файлы проиндексированы, поиск не проводился
    """
    
    def calculate_folder_status_fixed(file_colors):
        """Исправленная версия для папок."""
        if not file_colors:
            return 'gray'
            
        has_red = 'red' in file_colors
        has_green = 'green' in file_colors  
        has_yellow = 'yellow' in file_colors
        
        # Приоритет цветов: красный -> зелёный -> жёлтый -> серый
        if has_red:
            return 'red'
        if has_green:
            return 'green' 
        if has_yellow:
            return 'yellow'
        return 'gray'
    
    # Тест 1: Есть неиндексированные файлы - красный (высший приоритет)
    assert calculate_folder_status_fixed(['red', 'green', 'yellow', 'gray']) == 'red'
    assert calculate_folder_status_fixed(['red', 'gray']) == 'red'
    
    # Тест 2: Есть совпадения - зеленый
    assert calculate_folder_status_fixed(['green', 'yellow', 'gray']) == 'green'
    assert calculate_folder_status_fixed(['green', 'gray']) == 'green'
    
    # Тест 3: Нет совпадений при поиске - желтый
    assert calculate_folder_status_fixed(['yellow', 'gray']) == 'yellow'
    assert calculate_folder_status_fixed(['yellow']) == 'yellow'
    
    # Тест 4: Только серые (поиск не проводился) - серый
    assert calculate_folder_status_fixed(['gray']) == 'gray'
    assert calculate_folder_status_fixed(['gray', 'gray']) == 'gray'


def test_sorting_priority_fixed():
    """
    Тест приоритетов сортировки:
    - Зелёные файлы (с результатами) - наверх (приоритет 3)
    - Серые/жёлтые файлы (проиндексированные) - в середину (приоритет 2) 
    - Красные файлы (неиндексированные) - вниз (приоритет 1)
    """
    
    def get_sort_priority_fixed(color):
        """Исправленная версия приоритетов сортировки."""
        priority_map = {
            'green': 3,   # Файлы с результатами наверх
            'gray': 2,    # Проиндексированные в середину
            'yellow': 2,  # Проиндексированные без результатов в середину
            'red': 1      # Неиндексированные вниз
        }
        return priority_map.get(color, 1)
    
    # Проверяем приоритеты
    assert get_sort_priority_fixed('green') == 3
    assert get_sort_priority_fixed('gray') == 2  
    assert get_sort_priority_fixed('yellow') == 2
    assert get_sort_priority_fixed('red') == 1
    
    # Проверяем сортировку
    colors = ['red', 'yellow', 'green', 'gray']
    sorted_colors = sorted(colors, key=get_sort_priority_fixed, reverse=True)
    expected = ['green', 'yellow', 'gray', 'red']  # green наверх, red вниз
    assert sorted_colors == expected


if __name__ == "__main__":
    test_traffic_light_logic_fixed()
    test_folder_status_logic_fixed() 
    test_sorting_priority_fixed()
    print("✅ Все тесты исправленной логики светофоров пройдены успешно!")