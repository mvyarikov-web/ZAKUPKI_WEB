"""
Тест для проверки новой логики светофоров файлов и папок.
"""


def test_traffic_light_logic_mock():
    """
    Простой тест-мок для проверки новой логики светофоров:
    - Красный: не проиндексированные файлы
    - Желтый: проиндексированные без совпадений при поиске
    - Зеленый: проиндексированные с совпадениями при поиске  
    - Серый: проиндексированные без поиска
    """
    
    def get_traffic_light_color(status, char_count=None, has_search_results=False, search_performed=False):
        """Моковая версия JavaScript функции для тестирования логики."""
        # Красный: не проиндексированные
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
    
    # Тест 1: Не проиндексированные файлы - красный
    assert get_traffic_light_color('error', 100, False, False) == 'red'
    assert get_traffic_light_color('unsupported', 50, False, False) == 'red' 
    assert get_traffic_light_color('processing', 0, False, False) == 'red'
    
    # Тест 2: Поиск выполнен, есть результаты - зеленый
    assert get_traffic_light_color('contains_keywords', 100, True, True) == 'green'
    assert get_traffic_light_color('no_keywords', 50, True, True) == 'green'
    
    # Тест 3: Поиск выполнен, нет результатов - желтый  
    assert get_traffic_light_color('contains_keywords', 100, False, True) == 'yellow'
    assert get_traffic_light_color('no_keywords', 50, False, True) == 'yellow'
    
    # Тест 4: Поиск не выполнялся - серый
    assert get_traffic_light_color('contains_keywords', 100, False, False) == 'gray'
    assert get_traffic_light_color('no_keywords', 50, False, False) == 'gray'
    assert get_traffic_light_color('not_checked', None, False, False) == 'gray'


def test_folder_status_logic_mock():
    """
    Тест логики статуса папок:
    - Красный: есть неиндексированные файлы
    - Зеленый: есть совпадения при поиске
    - Желтый: нет совпадений при поиске, но файлы проиндексированы
    - Серый: файлы проиндексированы, поиск не проводился
    """
    
    def calculate_folder_status(file_colors):
        """Моковая версия для тестирования логики папок."""
        has_red = 'red' in file_colors
        has_green = 'green' in file_colors  
        has_yellow = 'yellow' in file_colors
        
        # Приоритет цветов
        if has_red:
            return 'red'
        if has_green:
            return 'green' 
        if has_yellow:
            return 'yellow'
        return 'gray'
    
    # Тест 1: Есть неиндексированные файлы - красный (высший приоритет)
    assert calculate_folder_status(['red', 'green', 'yellow', 'gray']) == 'red'
    assert calculate_folder_status(['red', 'gray']) == 'red'
    
    # Тест 2: Есть совпадения - зеленый
    assert calculate_folder_status(['green', 'yellow', 'gray']) == 'green'
    assert calculate_folder_status(['green', 'gray']) == 'green'
    
    # Тест 3: Нет совпадений при поиске - желтый
    assert calculate_folder_status(['yellow', 'gray']) == 'yellow'
    assert calculate_folder_status(['yellow']) == 'yellow'
    
    # Тест 4: Только серые (поиск не проводился) - серый
    assert calculate_folder_status(['gray']) == 'gray'
    assert calculate_folder_status(['gray', 'gray']) == 'gray'


if __name__ == "__main__":
    test_traffic_light_logic_mock()
    test_folder_status_logic_mock()
    print("✅ Все тесты логики светофоров пройдены успешно!")