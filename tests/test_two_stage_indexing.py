"""Минимальные тесты для двухэтапной индексации."""
import pytest
from datetime import datetime, timedelta
from document_processor.search.two_stage_indexer import TwoStageIndexer, IndexingStageResult


def test_two_stage_indexer_creation():
    """Создание экземпляра TwoStageIndexer."""
    indexer = TwoStageIndexer(max_depth=10, archive_depth=0)
    assert indexer is not None
    assert indexer.max_depth == 10
    assert indexer.archive_depth == 0


def test_get_extension():
    """Извлечение расширения файла."""
    assert TwoStageIndexer._get_extension("test.txt") == "txt"
    assert TwoStageIndexer._get_extension("document.PDF") == "pdf"
    assert TwoStageIndexer._get_extension("archive.zip") == "zip"
    assert TwoStageIndexer._get_extension("noext") == ""
    assert TwoStageIndexer._get_extension("multi.part.docx") == "docx"


def test_stage_result_duration():
    """Расчёт длительности этапа."""
    start = datetime.now()
    result = IndexingStageResult(
        stage=1,
        total_files=10,
        processed_files=10,
        skipped_files=0,
        errors=[],
        start_time=start
    )
    
    # Без завершения
    assert result.duration_seconds == 0.0
    
    # С завершением
    result.end_time = start + timedelta(seconds=5)
    assert result.duration_seconds == pytest.approx(5.0, abs=0.1)


@pytest.mark.timeout(5)
def test_simple_text_indexing(tmp_path):
    """Быстрая индексация одного текстового файла."""
    # Создаём один простой файл
    (tmp_path / "test.txt").write_text("Простой текст", encoding='utf-8')
    
    indexer = TwoStageIndexer()
    stage1, stage2 = indexer.create_index_two_stage(str(tmp_path))
    
    # Проверяем этап 1
    assert stage1 is not None
    assert stage1.stage == 1
    assert stage1.total_files >= 1
    
    # Этап 2 не должен быть выполнен
    assert stage2 is None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--timeout=10'])
