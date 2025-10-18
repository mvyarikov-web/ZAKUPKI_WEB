"""Минимальный тест real-time прогресса через SSE."""
import os
import pytest
from document_processor.search.two_stage_indexer import TwoStageIndexer


@pytest.mark.timeout(10)
def test_progress_callback_called(tmp_path):
    """Проверяет, что progress_callback вызывается при индексации."""
    # Создаём 3 простых текстовых файла
    for i in range(3):
        f = tmp_path / f"test_{i}.txt"
        f.write_text(f"Тест {i}", encoding='utf-8')
    
    # Счётчики вызовов колбэка
    callbacks = []
    
    def progress_callback(stage, processed, total, filename):
        callbacks.append({
            'stage': stage,
            'processed': processed,
            'total': total,
            'filename': filename
        })
    
    # Создаём индексатор и запускаем
    indexer = TwoStageIndexer(max_depth=1, archive_depth=0)
    stage1, stage2 = indexer.create_index_two_stage(
        str(tmp_path),
        progress_callback=progress_callback
    )
    
    # Проверяем, что колбэк вызывался
    assert len(callbacks) > 0, "Колбэк не вызывался"
    
    # Проверяем, что total > 0
    assert callbacks[0]['total'] == 3, f"Ожидалось 3 файла, получено {callbacks[0]['total']}"
    
    # Проверяем, что processed увеличивается
    processed_values = [c['processed'] for c in callbacks]
    assert max(processed_values) >= 3, f"Ожидалось >= 3 обработанных, max={max(processed_values)}"
    
    print(f"\n✓ Колбэк вызван {len(callbacks)} раз")
    print(f"✓ Обработано файлов: {max(processed_values)}/{callbacks[0]['total']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
