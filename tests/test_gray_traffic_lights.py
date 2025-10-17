"""
Тесты для проверки серого статуса светофоров и исключения непроиндексированных файлов.
Минимальный набор тестов с таймаутами.
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
            
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


class TestGrayTrafficLights:
    """Тесты серого статуса и обратного поиска."""
    
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
    def test_indexed_files_gray_before_search(self, client, app):
        """
        Тест: проиндексированные файлы до поиска должны быть серыми.
        """
        with app.app_context():
            uploads_dir = app.config['UPLOADS_FOLDER']
            
            # Создаем тестовый файл
            test_file = os.path.join(uploads_dir, 'test_gray.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Тестовое содержимое документа.')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Проверяем статус файла ДО поиска
            response = client.get('/files_json')
            assert response.status_code == 200
            files_data = response.get_json()
            
            file_status = files_data['file_statuses'].get('test_gray.txt')
            assert file_status is not None, "Файл должен быть в статусах"
            assert file_status.get('char_count', 0) > 0, "Файл должен быть проиндексирован"
            
            # Ключевое: проверяем, что статус не 'contains_keywords' (не было поиска)
            # Статус должен быть not_checked, processing или подобное (но НЕ contains_keywords/no_keywords без поиска)
            status = file_status.get('status', '')
            # До поиска файл не должен иметь статусы, связанные с поиском
            assert status not in ['contains_keywords', 'no_keywords'], \
                f"До поиска статус не должен быть {status}, должен быть нейтральный"
            
            print("✅ Проиндексированный файл имеет нейтральный статус до поиска")
    
    @pytest.mark.timeout(30)
    @timeout(30)
    def test_exclude_mode_skips_unindexed_files(self, client, app):
        """
        Тест: в режиме обратного поиска непроиндексированные файлы не должны выводиться.
        """
        with app.app_context():
            uploads_dir = app.config['UPLOADS_FOLDER']
            
            # Файл 1: проиндексированный
            test_file1 = os.path.join(uploads_dir, 'indexed.txt')
            with open(test_file1, 'w', encoding='utf-8') as f:
                f.write('Содержимое без ключевого слова контракт.')
            
            # Файл 2: неподдерживаемый формат (не будет проиндексирован)
            test_file2 = os.path.join(uploads_dir, 'unindexed.xyz')
            with open(test_file2, 'w', encoding='utf-8') as f:
                f.write('Неподдерживаемый формат')
            
            # Строим индекс
            response = client.post('/build_index')
            assert response.status_code == 200
            
            # Проверяем статусы
            response = client.get('/files_json')
            files_data = response.get_json()
            
            file1_status = files_data['file_statuses'].get('indexed.txt')
            file2_status = files_data['file_statuses'].get('unindexed.xyz')
            
            assert file1_status and file1_status.get('char_count', 0) > 0, \
                "Файл 1 должен быть проиндексирован"
            assert file2_status and file2_status.get('char_count', 0) == 0, \
                "Файл 2 не должен быть проиндексирован"
            
            # Выполняем ОБРАТНЫЙ поиск (exclude_mode=True)
            response = client.post('/search', 
                                   json={'search_terms': 'контракт', 'exclude_mode': True},
                                   content_type='application/json')
            assert response.status_code == 200
            
            search_data = response.get_json()
            results = search_data.get('results', [])
            
            # Проверяем, что в результатах только проиндексированные файлы
            result_files = [r.get('filename') for r in results]
            
            assert 'indexed.txt' in result_files, \
                "Проиндексированный файл без ключевого слова должен быть в результатах"
            assert 'unindexed.xyz' not in result_files, \
                "Непроиндексированный файл НЕ должен быть в результатах обратного поиска"
            
            print("✅ Обратный поиск корректно исключает непроиндексированные файлы")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
