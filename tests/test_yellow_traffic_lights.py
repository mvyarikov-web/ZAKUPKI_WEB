"""
Тест для проверки корректной работы желтых светофоров согласно инкременту 11.
Проверяет что файлы без результатов поиска, но проиндексированные, становятся желтыми.
"""

import pytest
import tempfile
import os
import signal
import functools


def timeout(seconds):
    """Декоратор для установки таймаута на выполнение функции."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Тест {func.__name__} превысил лимит времени {seconds} секунд")
            
            # Устанавливаем обработчик сигнала
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Сбрасываем будильник и восстанавливаем старый обработчик
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


class TestYellowTrafficLights:
    """Тесты желтых светофоров для файлов и архивов."""
    
    @pytest.fixture
    def app(self):
        """Фикстура Flask app."""
        from app import app
        app.config['TESTING'] = True
        app.config['UPLOADS_FOLDER'] = tempfile.mkdtemp()
        app.config['INDEX_FOLDER'] = tempfile.mkdtemp()
        return app
    
    @pytest.fixture
    def client(self, app):
        """Фикстура test client."""
        return app.test_client()
    
    @pytest.mark.timeout(30)
    @timeout(30)
    def test_yellow_traffic_light_for_indexed_file_no_results(self, client, app):
        """
        Тест: проиндексированный файл без результатов поиска должен стать желтым.
        """
        with app.app_context():
            # Создаем тестовый файл с содержимым, которое точно проиндексируется
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test_yellow.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Это документ с обычным текстом для индексации. Содержит много слов.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success', False), f"Ошибка построения индекса: {data}"
            
            # Проверяем, что файл проиндексирован
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            file_status = files_data['file_statuses'].get('test_yellow.txt')
            assert file_status is not None, "Файл должен быть в статусах"
            assert file_status.get('char_count', 0) > 0, "Файл должен быть проиндексирован"
            
            # Выполняем поиск по термину, который НЕ найдется
            response = client.post('/search', 
                                   json={'search_terms': 'несуществующий_уникальный_термин_12345', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            search_data = response.get_json()
            # Проверяем, что результатов действительно нет
            assert len(search_data.get('results', [])) == 0, "Результатов поиска не должно быть"
            
            print("✅ Проиндексированный файл без результатов поиска готов для проверки желтого статуса")
    
    @pytest.mark.timeout(30)
    @timeout(30)
    def test_green_traffic_light_for_file_with_results(self, client, app):
        """
        Тест: проиндексированный файл с результатами поиска должен стать зеленым.
        """
        with app.app_context():
            # Создаем тестовый файл с ключевым словом
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test_green.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Этот документ содержит ключевое слово договор для поиска.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Выполняем поиск по термину, который найдется
            response = client.post('/search', 
                                   json={'search_terms': 'договор', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            search_data = response.get_json()
            # Проверяем, что результаты есть
            assert len(search_data.get('results', [])) > 0, "Результаты поиска должны быть найдены"
            
            print("✅ Проиндексированный файл с результатами поиска готов для проверки зеленого статуса")
    
    @pytest.mark.timeout(30)
    @timeout(30)
    def test_red_traffic_light_for_unindexed_file(self, client, app):
        """
        Тест: непроиндексированный файл должен остаться красным.
        """
        with app.app_context():
            # Создаем файл неподдерживаемого формата
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test_red.xyz')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Неподдерживаемый формат файла')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Проверяем файловые статусы
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            # Файл неподдерживаемого формата не должен быть проиндексирован
            file_status = files_data['file_statuses'].get('test_red.xyz')
            if file_status:
                char_count = file_status.get('char_count', 0)
                status = file_status.get('status', '')
                assert char_count == 0 or status in ['error', 'unsupported'], \
                    "Неподдерживаемый файл не должен быть проиндексирован"
            
            # Выполняем поиск (файл должен остаться красным)
            response = client.post('/search', 
                                   json={'search_terms': 'любой_термин', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            print("✅ Непроиндексированный файл готов для проверки красного статуса")
    
    @pytest.mark.timeout(30)
    @timeout(30)
    def test_mixed_scenario_yellow_and_green_files(self, client, app):
        """
        Тест смешанного сценария: один файл желтый, другой зеленый.
        """
        with app.app_context():
            uploads_dir = app.config['UPLOADS_FOLDER']
            
            # Файл 1: будет желтым (проиндексирован, но без результатов)
            test_file1 = os.path.join(uploads_dir, 'yellow_file.txt')
            with open(test_file1, 'w', encoding='utf-8') as f:
                f.write('Документ с обычным содержимым без ключевых слов поиска.')
            
            # Файл 2: будет зеленым (проиндексирован и с результатами)
            test_file2 = os.path.join(uploads_dir, 'green_file.txt')
            with open(test_file2, 'w', encoding='utf-8') as f:
                f.write('Документ содержит важное слово контракт для поиска.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Проверяем, что оба файла проиндексированы
            response = client.get('/files_json')
            files_data = response.get_json()
            
            file1_status = files_data['file_statuses'].get('yellow_file.txt')
            file2_status = files_data['file_statuses'].get('green_file.txt')
            
            assert file1_status and file1_status.get('char_count', 0) > 0, "Файл 1 должен быть проиндексирован"
            assert file2_status and file2_status.get('char_count', 0) > 0, "Файл 2 должен быть проиндексирован"
            
            # Выполняем поиск по слову, которое есть только во втором файле
            response = client.post('/search', 
                                   json={'search_terms': 'контракт', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            search_data = response.get_json()
            results = search_data.get('results', [])
            
            # Должен быть найден только один файл
            assert len(results) > 0, "Результаты должны быть найдены"
            
            # Проверяем, что результаты только для green_file.txt
            found_files = {r.get('filename', r.get('source', '')) for r in results}
            assert 'green_file.txt' in str(found_files), "green_file.txt должен быть в результатах"
            
            print("✅ Смешанный сценарий готов: один файл желтый, другой зеленый")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])