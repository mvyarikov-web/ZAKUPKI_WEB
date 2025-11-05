"""
Тест интеграции модуля traffic-lights.js с основным приложением.
Проверяет, что модуляризация не сломала работу светофоров.
"""
import pytest
import requests


def test_traffic_lights_module_integration():
    """Тест интеграции модуля traffic-lights.js с HTML страницей."""
    try:
        # Проверяем, что сервер доступен
        response = requests.get('http://127.0.0.1:8081/health', timeout=5)
        assert response.status_code == 200
        
        # Проверяем главную страницу
        response = requests.get('http://127.0.0.1:8081/', timeout=5)
        assert response.status_code == 200
        html_content = response.text
        
        # Проверяем, что подключен модуль traffic-lights.js
        assert 'js/traffic-lights.js' in html_content, "Модуль traffic-lights.js не подключен к HTML"
        
        # Проверяем, что основной script.js подключен после модуля
        traffic_pos = html_content.find('js/traffic-lights.js')
        script_pos = html_content.find('js/script.js')
        assert traffic_pos < script_pos, "Модуль traffic-lights.js должен подключаться перед script.js"
        
        print("✅ Модуль traffic-lights.js корректно интегрирован в HTML")
        
    except requests.exceptions.ConnectionError:
        pytest.skip("Сервер не запущен на http://127.0.0.1:8081")


def test_traffic_lights_javascript_content():
    """Проверяем, что JavaScript модуль содержит нужные функции."""
    try:
        # Получаем содержимое модуля
        response = requests.get('http://127.0.0.1:8081/static/js/traffic-lights.js', timeout=5)
        assert response.status_code == 200
        js_content = response.text
        
        # Проверяем наличие ключевых функций и констант
        assert 'window.TrafficLights' in js_content, "Глобальный объект window.TrafficLights не найден"
        assert 'getFileTrafficLightColor' in js_content, "Функция getFileTrafficLightColor не найдена"
        assert 'getFolderTrafficLightColor' in js_content, "Функция getFolderTrafficLightColor не найдена"
        assert 'hasSearchResultsForFile' in js_content, "Функция hasSearchResultsForFile не найдена"
        assert 'isSearchPerformed' in js_content, "Функция isSearchPerformed не найдена"
        assert 'COLORS' in js_content, "Константы COLORS не найдены"
        
        # Проверяем цветовые константы
        assert 'RED: "red"' in js_content, "Константа RED не найдена"
        assert 'YELLOW: "yellow"' in js_content, "Константа YELLOW не найдена"
        assert 'GREEN: "green"' in js_content, "Константа GREEN не найдена"
        assert 'GRAY: "gray"' in js_content, "Константа GRAY не найдена"
        
        print("✅ JavaScript модуль содержит все необходимые функции и константы")
        
    except requests.exceptions.ConnectionError:
        pytest.skip("Сервер не запущен на http://127.0.0.1:8081")


if __name__ == "__main__":
    test_traffic_lights_module_integration()
    test_traffic_lights_javascript_content()
    print("✅ Все тесты интеграции модуля светофоров пройдены успешно!")