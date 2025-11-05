import shutil
import subprocess
from pathlib import Path
import pytest

from document_processor import DocumentProcessor


@pytest.mark.skipif(
    (shutil.which("unrar") is None and shutil.which("unar") is None) or shutil.which("rar") is None,
    reason="Требуются утилиты 'rar' для создания и 'unrar'/'unar' для чтения"
)
def test_rar_archive_full_indexing(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    # Подготовим структуру для упаковки в RAR
    staging = tmp_path / "staging"
    (staging / "docs").mkdir(parents=True)
    (staging / "docs" / "readme.txt").write_text("Привет из RAR архива", encoding="utf-8")

    rar_path = root / "data.rar"

    # Создаём RAR-архив: rar a <archive> <files>
    cmd = [shutil.which("rar"), "a", str(rar_path), str(staging / "docs" / "readme.txt")]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"rar a failed: {res.stderr.decode(errors='ignore')}"

    # Индексация
    dp = DocumentProcessor()
    dp.create_search_index(str(root))

    text = (root / "_search_index.txt").read_text(encoding="utf-8", errors="ignore")
    assert "rar://data.rar!/docs/readme.txt" in text
    assert "Привет из RAR архива" in text
