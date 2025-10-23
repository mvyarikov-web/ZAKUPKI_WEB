"""
Тест для проверки построения индекса и его состояния.
Проверяет работоспособность эндпоинтов /build_index и /index_status.
"""
import pytest
import time
import json
from pathlib import Path


def test_index_build_and_status(tmp_path):
    """
    Полный тест построения индекса:
    1. Создание тестовых файлов
    2. Запуск построения индекса
    3. Опрос статуса индекса
    4. Проверка завершения
    """
    from webapp import create_app
    
    # Подготовка структуры
    uploads = tmp_path / 'uploads'
    index_dir = tmp_path / 'index'
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)
    
    # Создаём тестовые файлы разных типов
    (uploads / 'test1.txt').write_text('Тестовый файл номер один', encoding='utf-8')
    (uploads / 'test2.txt').write_text('Второй тестовый файл', encoding='utf-8')
    (uploads / 'test3.txt').write_text('Третий файл для проверки', encoding='utf-8')
    
    # Создаём приложение
    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)
    
    with app.test_client() as client:
        # 1. Проверка статуса ДО построения индекса
        print("\n=== Проверка статуса ДО построения индекса ===")
        resp = client.get('/index_status')
        assert resp.status_code == 200, f"Ошибка /index_status: {resp.status_code}"
        
        data = resp.get_json()
        print(f"Статус до построения: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 2. Запуск построения индекса
        print("\n=== Запуск построения индекса ===")
        resp = client.post('/build_index', 
                          json={'use_groups': True},
                          content_type='application/json')
        assert resp.status_code == 200, f"Ошибка /build_index: {resp.status_code}"
        
        build_data = resp.get_json()
        print(f"Ответ build_index: {json.dumps(build_data, ensure_ascii=False, indent=2)}")
        assert build_data.get('success'), f"build_index вернул success=False: {build_data}"
        
        # 3. Опрос статуса с таймаутом
        print("\n=== Опрос статуса индексации ===")
        timeout = 30  # 30 секунд максимум
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            resp = client.get('/index_status')
            assert resp.status_code == 200, f"Ошибка /index_status: {resp.status_code}"
            
            data = resp.get_json()
            
            # Проверяем, что нет ошибки
            if 'error' in data:
                pytest.fail(f"index_status вернул ошибку: {data['error']}")
            
            last_status = data
            status = data.get('status', 'unknown')
            group_status = data.get('group_status', {})
            
            print(f"[{time.time() - start_time:.1f}s] Статус: {status}, Группы: {group_status}")
            
            # Проверка на завершение
            if status == 'completed':
                print("✅ Индексация завершена!")
                break
            
            if status == 'error':
                pytest.fail(f"Индексация завершилась с ошибкой: {data}")
            
            time.sleep(1)
        else:
            pytest.fail(f"Таймаут ожидания завершения индексации. Последний статус: {last_status}")
        
        # 4. Финальные проверки
        print("\n=== Финальные проверки ===")
        assert last_status.get('exists'), "Индекс должен существовать"
        assert last_status.get('status') == 'completed', f"Статус должен быть 'completed', получен: {last_status.get('status')}"
        assert last_status.get('entries', 0) > 0, "Индекс должен содержать записи"
        
        # Проверка файла индекса
        index_path = index_dir / '_search_index.txt'
        assert index_path.exists(), f"Файл индекса не найден: {index_path}"
        
        index_content = index_path.read_text(encoding='utf-8')
        assert 'test1.txt' in index_content, "Файл test1.txt должен быть в индексе"
        assert 'test2.txt' in index_content, "Файл test2.txt должен быть в индексе"
        assert 'test3.txt' in index_content, "Файл test3.txt должен быть в индексе"
        
        print(f"✅ Индекс создан: {index_path}")
        print(f"✅ Размер: {last_status.get('size', 0)} байт")
        print(f"✅ Записей: {last_status.get('entries', 0)}")
        print(f"✅ Статус групп: {last_status.get('group_status', {})}")
        
        return True


def test_index_status_endpoint_error_handling(tmp_path):
    """Проверка обработки ошибок в /index_status."""
    from webapp import create_app
    
    # Пустая папка без файлов
    uploads = tmp_path / 'uploads'
    index_dir = tmp_path / 'index'
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)
    
    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)
    
    with app.test_client() as client:
        resp = client.get('/index_status')
        assert resp.status_code == 200
        
        data = resp.get_json()
        
        # Не должно быть ошибки даже при отсутствии файлов
        assert 'error' not in data, f"Не должно быть ошибки: {data}"
        assert data.get('exists') == False, "Индекс не должен существовать для пустой папки"


def test_index_status_without_datetime_error(tmp_path):
    """Проверка, что нет ошибки 'datetime referenced before assignment'."""
    from webapp import create_app
    
    uploads = tmp_path / 'uploads'
    index_dir = tmp_path / 'index'
    uploads.mkdir(parents=True)
    index_dir.mkdir(parents=True)
    
    # Создаём хотя бы один файл
    (uploads / 'test.txt').write_text('test', encoding='utf-8')
    
    app = create_app('testing')
    app.config['UPLOAD_FOLDER'] = str(uploads)
    app.config['INDEX_FOLDER'] = str(index_dir)
    
    with app.test_client() as client:
        # Сначала построим индекс
        client.post('/build_index', json={'use_groups': True})
        time.sleep(2)  # Даём время на построение
        
        # Проверяем статус
        resp = client.get('/index_status')
        assert resp.status_code == 200
        
        data = resp.get_json()
        print(f"Ответ index_status: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # Главное — не должно быть ошибки про datetime
        assert 'error' not in data or 'datetime' not in data.get('error', ''), \
            f"Ошибка datetime найдена: {data}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
