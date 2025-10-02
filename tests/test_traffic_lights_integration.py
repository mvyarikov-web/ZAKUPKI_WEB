"""
Интеграционный тест для проверки исправления бага светофоров.
Тестирует сценарий из issue: "после первого поиска непроиндексированные файлы стали зелеными".
"""
import pytest
import tempfile
import os
from webapp import create_app
from webapp.services.state import FilesState


@pytest.fixture
def app():
    """Создаёт тестовое приложение Flask."""
    test_app = create_app()
    test_app.config['TESTING'] = True
    
    # Создаём временные директории
    test_app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    test_app.config['INDEX_FOLDER'] = tempfile.mkdtemp()
    test_app.config['SEARCH_RESULTS_FILE'] = os.path.join(
        test_app.config['INDEX_FOLDER'], 'search_results.json'
    )
    
    yield test_app


@pytest.fixture
def client(app):
    """Создаёт тестовый клиент."""
    return app.test_client()


@pytest.fixture
def test_files(app):
    """Создаёт тестовые файлы: проиндексированный и неиндексированный."""
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Файл 1: Проиндексированный (TXT с содержимым про монтаж)
    indexed_file = os.path.join(upload_folder, 'indexed_file.txt')
    with open(indexed_file, 'w', encoding='utf-8') as f:
        f.write('Документация по монтажу оборудования.')
    
    # Файл 2: Неиндексированный (пустой файл)
    unindexed_file = os.path.join(upload_folder, 'unindexed_file.txt')
    with open(unindexed_file, 'w', encoding='utf-8') as f:
        f.write('')  # Пустой файл = char_count = 0 = неиндексированный
    
    # Файл 3: Проиндексированный без совпадений (TXT с содержимым про другое)
    no_match_file = os.path.join(upload_folder, 'no_match_file.txt')
    with open(no_match_file, 'w', encoding='utf-8') as f:
        f.write('Инструкция по эксплуатации.')
    
    return {
        'indexed': 'indexed_file.txt',
        'unindexed': 'unindexed_file.txt', 
        'no_match': 'no_match_file.txt'
    }


def test_bug_unindexed_files_turned_green_after_search(client, app, test_files):
    """
    Тест бага: "после первого поиска непроиндексированные файлы стали зелеными".
    
    Упрощённая версия: проверяем только логику светофоров без реального поиска.
    """
    with app.app_context():
        # Шаг 1: Строим индекс
        response = client.post('/build_index')
        assert response.status_code == 200
        
        # Шаг 2: Получаем статусы файлов ДО поиска
        fs = FilesState(app.config['SEARCH_RESULTS_FILE'])
        
        indexed_status = fs.get_file_status(test_files['indexed'])
        unindexed_status = fs.get_file_status(test_files['unindexed'])
        no_match_status = fs.get_file_status(test_files['no_match'])
        
        # Проверяем статусы ДО поиска
        assert indexed_status.get('char_count', 0) > 0, "Проиндексированный файл должен иметь char_count > 0"
        assert unindexed_status.get('char_count', 0) == 0, "Неиндексированный файл должен иметь char_count = 0"
        assert no_match_status.get('char_count', 0) > 0, "Файл без совпадений должен иметь char_count > 0"
        
        # Проверяем цвета ДО поиска (используя Python логику)
        from webapp.utils.traffic_lights import TrafficLightLogic
        
        # До поиска: searchPerformed = False
        indexed_color_before = TrafficLightLogic.get_file_traffic_light_color(
            indexed_status.get('status', 'not_checked'),
            indexed_status.get('char_count', 0),
            has_search_results=False,
            search_performed=False
        )
        
        unindexed_color_before = TrafficLightLogic.get_file_traffic_light_color(
            unindexed_status.get('status', 'error'),
            unindexed_status.get('char_count', 0),
            has_search_results=False,
            search_performed=False
        )
        
        no_match_color_before = TrafficLightLogic.get_file_traffic_light_color(
            no_match_status.get('status', 'not_checked'),
            no_match_status.get('char_count', 0),
            has_search_results=False,
            search_performed=False
        )
        
        # Проверка: до поиска проиндексированные файлы серые, неиндексированные красные
        assert indexed_color_before == 'gray', f"До поиска проиндексированный файл должен быть серым, получен {indexed_color_before}"
        assert unindexed_color_before == 'red', f"До поиска неиндексированный файл должен быть красным, получен {unindexed_color_before}"
        assert no_match_color_before == 'gray', f"До поиска файл без совпадений должен быть серым, получен {no_match_color_before}"
        
        # Шаг 3: Симулируем поиск - проверяем цвета ПОСЛЕ поиска
        # После поиска: searchPerformed = True
        
        # indexed_file: симулируем что есть результаты поиска
        indexed_color_after = TrafficLightLogic.get_file_traffic_light_color(
            indexed_status.get('status', 'contains_keywords'),
            indexed_status.get('char_count', 0),
            has_search_results=True,  # Есть совпадения
            search_performed=True
        )
        
        # unindexed_file: неиндексированный, даже если искусственно установить has_search_results=True
        unindexed_color_after_no_results = TrafficLightLogic.get_file_traffic_light_color(
            unindexed_status.get('status', 'error'),
            unindexed_status.get('char_count', 0),
            has_search_results=False,  # Нет результатов
            search_performed=True
        )
        
        # ГЛАВНАЯ ПРОВЕРКА БАГА: даже если has_search_results=True для неиндексированного
        unindexed_color_after_fake_results = TrafficLightLogic.get_file_traffic_light_color(
            unindexed_status.get('status', 'error'),
            unindexed_status.get('char_count', 0),
            has_search_results=True,  # Искусственно установленные результаты
            search_performed=True
        )
        
        # no_match_file: проиндексированный, но нет совпадений
        no_match_color_after = TrafficLightLogic.get_file_traffic_light_color(
            no_match_status.get('status', 'no_keywords'),
            no_match_status.get('char_count', 0),
            has_search_results=False,  # Нет совпадений
            search_performed=True
        )
        
        # ПРОВЕРКИ
        assert indexed_color_after == 'green', f"После поиска файл с совпадениями должен быть зелёным, получен {indexed_color_after}"
        assert unindexed_color_after_no_results == 'red', f"❌ БАГ: После поиска неиндексированный файл должен оставаться красным, получен {unindexed_color_after_no_results}"
        assert unindexed_color_after_fake_results == 'red', f"❌ БАГ: Неиндексированный файл НИКОГДА не должен быть зелёным, даже с has_search_results=True, получен {unindexed_color_after_fake_results}"
        assert no_match_color_after == 'yellow', f"После поиска файл без совпадений должен быть жёлтым, получен {no_match_color_after}"
        
        print("\n✅ Тест пройден! Неиндексированные файлы остаются красными после поиска.")


def test_unindexed_file_never_turns_green_even_with_fake_results(client, app, test_files):
    """
    Тест проверяет, что даже если мы искусственно установим has_search_results=True
    для неиндексированного файла, он всё равно останется красным.
    """
    with app.app_context():
        from webapp.utils.traffic_lights import TrafficLightLogic
        
        # Неиндексированный файл с различными комбинациями параметров
        # Все должны возвращать RED
        
        # Сценарий 1: До поиска
        color1 = TrafficLightLogic.get_file_traffic_light_color(
            'error', 0, has_search_results=False, search_performed=False
        )
        assert color1 == 'red', "Неиндексированный файл до поиска должен быть красным"
        
        # Сценарий 2: После поиска, нет результатов
        color2 = TrafficLightLogic.get_file_traffic_light_color(
            'error', 0, has_search_results=False, search_performed=True
        )
        assert color2 == 'red', "Неиндексированный файл после поиска без результатов должен быть красным"
        
        # Сценарий 3: После поиска, есть результаты (искусственный случай)
        # ЭТО И ЕСТЬ БАГ, КОТОРЫЙ МЫ ИСПРАВИЛИ!
        color3 = TrafficLightLogic.get_file_traffic_light_color(
            'error', 0, has_search_results=True, search_performed=True
        )
        assert color3 == 'red', "❌ БАГ: Неиндексированный файл НИКОГДА не должен быть зелёным, даже с has_search_results=True"
        
        # Сценарий 4: Unsupported файл
        color4 = TrafficLightLogic.get_file_traffic_light_color(
            'unsupported', 50, has_search_results=True, search_performed=True
        )
        assert color4 == 'red', "❌ БАГ: Unsupported файл НИКОГДА не должен быть зелёным"
        
        print("\n✅ Тест пройден! Неиндексированные файлы НИКОГДА не становятся зелёными.")


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
