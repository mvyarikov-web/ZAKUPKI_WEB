"""Быстрый интеграционный тест для проверки счетчиков совпадений."""
import pytest
import tempfile
import os
from pathlib import Path
from webapp import create_app
from webapp.services.indexing import build_search_index


def test_search_counters_not_doubled(tmp_path):
    """Проверяем, что счетчики совпадений не задваиваются после исправления."""
    # Создаём тестовые файлы с известным количеством совпадений
    test_file1 = tmp_path / "test1.txt"
    test_file1.write_text("договор один договор два договор три", encoding='utf-8')
    
    test_file2 = tmp_path / "test2.txt"  
    test_file2.write_text("поставка материалов по договору номер пять", encoding='utf-8')
    
    # Настраиваем тестовое приложение
    app = create_app()
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    app.config['INDEX_FOLDER'] = str(tmp_path / 'index')
    
    with app.test_client() as client:
        with app.app_context():
            # Создаём индекс
            build_search_index(str(tmp_path), app.config['INDEX_FOLDER'])
            
            # Выполняем поиск
            response = client.post('/search', 
                                 json={'search_terms': 'договор'})
            
            assert response.status_code == 200
            data = response.get_json()
            results = data.get('results', [])
            
            # Подсчитываем общее количество совпадений
            total_matches = 0
            expected_matches = 4  # 3 в test1.txt + 1 в test2.txt
            
            for result in results:
                per_term = result.get('per_term', [])
                for term_info in per_term:
                    if term_info.get('term') == 'договор':
                        count = term_info.get('count', 0)
                        total_matches += count
                        filename = result.get('filename', '')
                        print(f"Файл {filename}: {count} совпадений")
            
            print(f"Общее количество совпадений: {total_matches}")
            print(f"Ожидалось: {expected_matches}")
            
            # Проверяем, что количество совпадений правильное
            assert total_matches == expected_matches, \
                f"Ожидалось {expected_matches} совпадений, получено {total_matches}"
            
            # Проверяем, что нет задваивания (количество должно быть точным)
            assert total_matches < expected_matches * 2, \
                "Возможно задваивание результатов"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_search_counters_not_doubled(Path(tmp_dir))
    print("✓ Тест счетчиков совпадений пройден")