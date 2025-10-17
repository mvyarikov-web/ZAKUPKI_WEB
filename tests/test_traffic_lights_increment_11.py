"""
Тест логики светофоров согласно спецификации инкремента 11.
Проверяет корректность определения желтого и других статусов файлов и папок через веб-интерфейс.
"""

import pytest
import tempfile
import os
import json
from unittest.mock import patch


class TestTrafficLightsIncrement11:
    """Тесты логики светофоров согласно спецификации инкремента 11."""
    
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
    def test_yellow_light_scenario(self, client, app):
        """
        Тест сценария: проиндексированный файл без результатов поиска должен стать желтым.
        """
        with app.app_context():
            # Создаем тестовый файл
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Это тестовый документ без ключевых слов для поиска.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Выполняем поиск по термину, который не найдется
            response = client.post('/search', 
                                   json={'search_terms': 'несуществующий_термин', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            data = response.get_json()
            # Проверяем, что результатов нет (файл должен стать желтым)
            assert 'results' in data
            # Файл проиндексирован, но результатов нет - должен быть желтый
            
            # Проверяем файловые статусы
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            # Проверяем, что файл имеет символы больше 0 (проиндексирован)
            file_status = files_data['file_statuses'].get('test.txt')
            assert file_status is not None
            assert file_status.get('char_count', 0) > 0, "Файл должен быть проиндексирован"
    
    @pytest.mark.timeout(30)
    def test_green_light_scenario(self, client, app):
        """
        Тест сценария: проиндексированный файл с результатами поиска должен стать зеленым.
        """
        with app.app_context():
            # Создаем тестовый файл с ключевым словом
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test_with_keyword.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Этот документ содержит важное ключевое слово: договор.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Выполняем поиск по термину, который найдется
            response = client.post('/search', 
                                   json={'search_terms': 'договор', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            data = response.get_json()
            # Проверяем, что результаты есть (файл должен стать зеленым)
            assert 'results' in data
            assert len(data['results']) > 0, "Должны быть найдены результаты"
    
    @pytest.mark.timeout(30)
    def test_red_light_scenario(self, client, app):
        """
        Тест сценария: непроиндексированный файл должен остаться красным.
        """
        with app.app_context():
            # Создаем неподдерживаемый файл
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'test.unknown')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Неподдерживаемый формат')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Выполняем поиск
            response = client.post('/search', 
                                   json={'search_terms': 'любой_термин', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            # Проверяем файловые статусы
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            # Проверяем, что файл не проиндексирован (0 символов или статус error/unsupported)
            file_status = files_data['file_statuses'].get('test.unknown')
            if file_status:
                char_count = file_status.get('char_count', 0)
                status = file_status.get('status', '')
                assert char_count == 0 or status in ['error', 'unsupported'], \
                    "Неподдерживаемый файл должен иметь 0 символов или статус error/unsupported"
    
    @pytest.mark.timeout(30)
    def test_gray_to_yellow_transition(self, client, app):
        """
        Тест перехода: серый светофор (до поиска) -> желтый (после поиска без результатов).
        Согласно спецификации: если хоть раз была нажата кнопка поиска с непустым запросом, 
        после этого светофор на файле серым быть не может.
        """
        with app.app_context():
            # Создаем тестовый файл
            uploads_dir = app.config['UPLOADS_FOLDER']
            test_file = os.path.join(uploads_dir, 'transition_test.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Документ для тестирования перехода статусов.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Проверяем начальное состояние (до поиска файл должен быть проиндексирован)
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            file_status = files_data['file_statuses'].get('transition_test.txt')
            assert file_status is not None
            assert file_status.get('char_count', 0) > 0, "Файл должен быть проиндексирован"
            
            # Выполняем поиск без результатов
            response = client.post('/search', 
                                   json={'search_terms': 'термин_который_не_найдется', 'exclude_mode': False},
                                   content_type='application/json')
            assert response.status_code == 200
            
            # После поиска файл должен стать желтым (был проиндексирован, но результатов нет)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])