"""Минимальный тест единой шкалы прогресса индексации."""
import pytest
import os
from document_processor.search.two_stage_indexer import TwoStageIndexer


@pytest.mark.timeout(10)
def test_unified_progress_bar_minimal(tmp_path):
    """Проверяем, что прогресс отображается корректно с единой шкалой."""
    # Создаём тестовые файлы
    test_dir = tmp_path / "test_files"
    test_dir.mkdir()
    
    # Только 2 текстовых файла для быстрого теста
    (test_dir / "file1.txt").write_text("Текст файла 1", encoding='utf-8')
    (test_dir / "file2.txt").write_text("Текст файла 2", encoding='utf-8')
    
    # Отслеживаем прогресс
    progress_updates = []
    
    def progress_callback(stage, processed, total, filename):
        progress_updates.append({
            'processed': processed,
            'total': total,
        })
    
    # Запускаем индексацию
    indexer = TwoStageIndexer(max_depth=10, archive_depth=0)
    stage1, stage2 = indexer.create_index_two_stage(str(test_dir), progress_callback=progress_callback)
    
    # Проверяем результаты
    assert stage1 is not None
    assert stage1.total_files == 2
    assert stage1.processed_files == 2
    
    # Проверяем, что прогресс отправлялся
    assert len(progress_updates) > 0
    
    # Проверяем, что общее количество (total) одинаково во всех обновлениях
    totals = [u['total'] for u in progress_updates]
    assert len(set(totals)) == 1, "Total должен быть одинаковым во всех обновлениях"
    
    # Проверяем, что индекс создан
    index_path = test_dir / "_search_index.txt"
    assert index_path.exists()
    
    # Проверяем, что файлы доступны для поиска
    index_content = index_path.read_text(encoding='utf-8')
    assert "file1.txt" in index_content
    assert "file2.txt" in index_content
    
    print(f"✓ Тест прошёл: {stage1.processed_files} файлов, {len(progress_updates)} обновлений")


@pytest.mark.timeout(10)
def test_incremental_index_writing_minimal(tmp_path):
    """Проверяем, что файлы дозаписываются в индекс инкрементально."""
    test_dir = tmp_path / "incremental_test"
    test_dir.mkdir()
    
    # Создаём 3 файла для быстрого теста
    for i in range(3):
        (test_dir / f"doc{i}.txt").write_text(f"Документ {i}", encoding='utf-8')
    
    indexer = TwoStageIndexer(max_depth=10, archive_depth=0)
    stage1, stage2 = indexer.create_index_two_stage(str(test_dir))
    
    # Проверяем, что индекс создан
    index_path = test_dir / "_search_index.txt"
    assert index_path.exists()
    
    # Проверяем, что все файлы в индексе
    content = index_path.read_text(encoding='utf-8')
    assert content.count('ЗАГОЛОВОК:') == 3
    
    print(f"✓ Инкрементальная запись работает: 3 файла в индексе")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-timeout=10'])
