"""
Комплексные тесты для логики светофоров.
Проверяет все сценарии работы светофоров для файлов и папок.
"""
import pytest
from webapp.utils.traffic_lights import TrafficLightLogic


class TestFileTrafficLights:
    """Тесты светофоров для файлов."""
    
    def test_unindexed_file_always_red(self):
        """
        🔴 Неиндексированный файл всегда красный, независимо от результатов поиска.
        """
        # Статус error - всегда красный
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, False, False) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, False, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, True, True) == 'red'
        
        # Статус unsupported - всегда красный
        assert TrafficLightLogic.get_file_traffic_light_color('unsupported', 50, False, False) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('unsupported', 50, False, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('unsupported', 50, True, True) == 'red'
        
        # Нулевой char_count - всегда красный
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 0, False, False) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 0, False, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 0, True, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 0, True, True) == 'red'
    
    def test_indexed_file_before_search_is_gray(self):
        """
        ⚪ Проиндексированный файл до первого поиска - серый.
        """
        # Различные статусы проиндексированных файлов
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, False, False) == 'gray'
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, False, False) == 'gray'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 200, False, False) == 'gray'
        assert TrafficLightLogic.get_file_traffic_light_color('not_checked', None, False, False) == 'gray'
    
    def test_indexed_file_with_search_results_is_green(self):
        """
        🟢 Проиндексированный файл с совпадениями при поиске - зелёный.
        """
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, True, True) == 'green'
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, True, True) == 'green'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 200, True, True) == 'green'
    
    def test_indexed_file_without_search_results_is_yellow(self):
        """
        🟡 Проиндексированный файл без совпадений при поиске - жёлтый.
        """
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, False, True) == 'yellow'
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, False, True) == 'yellow'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 200, False, True) == 'yellow'
    
    def test_file_indexing_check(self):
        """
        Тест проверки индексации файла.
        """
        # Проиндексированные файлы
        assert TrafficLightLogic.is_file_indexed('contains_keywords', 100) == True
        assert TrafficLightLogic.is_file_indexed('no_keywords', 50) == True
        assert TrafficLightLogic.is_file_indexed('processing', 200) == True
        
        # Неиндексированные файлы
        assert TrafficLightLogic.is_file_indexed('error', 100) == False
        assert TrafficLightLogic.is_file_indexed('unsupported', 50) == False
        assert TrafficLightLogic.is_file_indexed('processing', 0) == False


class TestFolderTrafficLights:
    """Тесты светофоров для папок."""
    
    def test_folder_with_red_files_is_red(self):
        """
        🔴 Папка с хотя бы одним неиндексированным файлом - красная.
        Красный имеет высший приоритет.
        """
        # Красный + другие цвета = красный
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'green', 'yellow', 'gray']) == 'red'
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'green']) == 'red'
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'yellow']) == 'red'
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'gray']) == 'red'
        assert TrafficLightLogic.get_folder_traffic_light_color(['red']) == 'red'
        
        # Несколько красных
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'red', 'green']) == 'red'
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'red', 'red']) == 'red'
    
    def test_folder_with_green_files_is_green(self):
        """
        🟢 Папка с хотя бы одним файлом с совпадениями - зелёная.
        (При условии отсутствия красных файлов)
        """
        # Зелёный без красных = зелёный
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'yellow', 'gray']) == 'green'
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'yellow']) == 'green'
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'gray']) == 'green'
        assert TrafficLightLogic.get_folder_traffic_light_color(['green']) == 'green'
        
        # Несколько зелёных
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'green', 'yellow']) == 'green'
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'green', 'green']) == 'green'
    
    def test_folder_with_yellow_files_is_yellow(self):
        """
        🟡 Папка с проиндексированными файлами без совпадений - жёлтая.
        (При условии отсутствия красных и зелёных файлов)
        """
        # Жёлтый без красных и зелёных = жёлтый
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow', 'gray']) == 'yellow'
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow']) == 'yellow'
        
        # Несколько жёлтых
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow', 'yellow', 'gray']) == 'yellow'
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow', 'yellow', 'yellow']) == 'yellow'
    
    def test_folder_with_only_gray_files_is_gray(self):
        """
        ⚪ Папка только с серыми файлами (до поиска) - серая.
        """
        assert TrafficLightLogic.get_folder_traffic_light_color(['gray']) == 'gray'
        assert TrafficLightLogic.get_folder_traffic_light_color(['gray', 'gray']) == 'gray'
        assert TrafficLightLogic.get_folder_traffic_light_color(['gray', 'gray', 'gray']) == 'gray'
    
    def test_empty_folder_is_gray(self):
        """
        Пустая папка - серая.
        """
        assert TrafficLightLogic.get_folder_traffic_light_color([]) == 'gray'
        assert TrafficLightLogic.get_folder_traffic_light_color(None) == 'gray'
    
    def test_folder_priority_order(self):
        """
        Тест приоритета цветов для папок: красный > зелёный > жёлтый > серый.
        """
        # Приоритет 1: Красный > все остальные
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'green', 'yellow', 'gray']) == 'red'
        
        # Приоритет 2: Зелёный > жёлтый и серый (при отсутствии красного)
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'yellow', 'gray']) == 'green'
        
        # Приоритет 3: Жёлтый > серый (при отсутствии красного и зелёного)
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow', 'gray']) == 'yellow'
        
        # Приоритет 4: Серый (только при отсутствии всех остальных)
        assert TrafficLightLogic.get_folder_traffic_light_color(['gray', 'gray']) == 'gray'


class TestSortingPriority:
    """Тесты приоритета сортировки."""
    
    def test_sort_priority_values(self):
        """
        Тест значений приоритета сортировки:
        - Зелёный: 3 (наверх)
        - Серый/Жёлтый: 2 (в середину)
        - Красный: 1 (вниз)
        """
        assert TrafficLightLogic.get_sort_priority('green') == 3
        assert TrafficLightLogic.get_sort_priority('gray') == 2
        assert TrafficLightLogic.get_sort_priority('yellow') == 2
        assert TrafficLightLogic.get_sort_priority('red') == 1
    
    def test_sort_priority_order(self):
        """
        Тест сортировки по приоритету.
        """
        colors = ['red', 'yellow', 'green', 'gray']
        sorted_colors = sorted(colors, key=TrafficLightLogic.get_sort_priority, reverse=True)
        
        # Зелёные наверх, красные вниз
        assert sorted_colors[0] == 'green'
        assert sorted_colors[-1] == 'red'
        # Серый и жёлтый имеют одинаковый приоритет
        assert set(sorted_colors[1:3]) == {'yellow', 'gray'}


class TestSearchScenarios:
    """Тесты для различных сценариев поиска."""
    
    def test_before_first_search_all_indexed_are_gray(self):
        """
        До первого поиска все проиндексированные файлы - серые.
        """
        # Проиндексированные файлы до поиска
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, False, False) == 'gray'
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, False, False) == 'gray'
        
        # Неиндексированные файлы всегда красные
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, False, False) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('unsupported', 50, False, False) == 'red'
    
    def test_after_search_indexed_are_green_or_yellow(self):
        """
        После поиска проиндексированные файлы - зелёные (есть совпадения) или жёлтые (нет совпадений).
        """
        # С совпадениями = зелёный
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, True, True) == 'green'
        
        # Без совпадений = жёлтый
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, False, True) == 'yellow'
    
    def test_after_search_unindexed_still_red(self):
        """
        После поиска неиндексированные файлы остаются красными.
        """
        # Неиндексированные файлы всегда красные, даже если есть "совпадения"
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, True, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('unsupported', 50, True, True) == 'red'
        assert TrafficLightLogic.get_file_traffic_light_color('processing', 0, True, True) == 'red'
    
    def test_reverse_search_scenario(self):
        """
        Тест обратного поиска (exclude mode):
        - Зелёный: файл НЕ содержит искомые слова
        - Жёлтый: файл содержит искомые слова (не соответствует критерию)
        
        Логика определения совпадений обрабатывается на уровне поиска,
        светофоры просто отображают has_search_results.
        """
        # При обратном поиске "совпадение" = файл НЕ содержит слова
        # Зелёный = есть "совпадение" (файл прошёл фильтр)
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 100, True, True) == 'green'
        
        # Жёлтый = нет "совпадения" (файл не прошёл фильтр)
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, False, True) == 'yellow'


class TestArchiveScenarios:
    """Тесты для файлов внутри архивов."""
    
    def test_files_in_archive_follow_same_rules(self):
        """
        Файлы внутри архивов следуют тем же правилам светофоров.
        """
        # Неиндексированный файл в архиве - красный
        assert TrafficLightLogic.get_file_traffic_light_color('error', 100, False, False) == 'red'
        
        # Проиндексированный файл в архиве до поиска - серый
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, False, False) == 'gray'
        
        # Проиндексированный файл в архиве с совпадениями - зелёный
        assert TrafficLightLogic.get_file_traffic_light_color('contains_keywords', 100, True, True) == 'green'
        
        # Проиндексированный файл в архиве без совпадений - жёлтый
        assert TrafficLightLogic.get_file_traffic_light_color('no_keywords', 50, False, True) == 'yellow'
    
    def test_archive_folder_inherits_child_colors(self):
        """
        Архив (как папка) наследует цвета файлов внутри по тем же правилам приоритета.
        """
        # Архив с красными файлами - красный
        assert TrafficLightLogic.get_folder_traffic_light_color(['red', 'green']) == 'red'
        
        # Архив с зелёными файлами (без красных) - зелёный
        assert TrafficLightLogic.get_folder_traffic_light_color(['green', 'yellow']) == 'green'
        
        # Архив с жёлтыми файлами (без красных и зелёных) - жёлтый
        assert TrafficLightLogic.get_folder_traffic_light_color(['yellow', 'gray']) == 'yellow'
        
        # Архив с серыми файлами - серый
        assert TrafficLightLogic.get_folder_traffic_light_color(['gray', 'gray']) == 'gray'


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
