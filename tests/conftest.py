import sys
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Tuple
import pytest

# Добавляем корневую директорию проекта в PYTHONPATH для импорта webapp
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Устанавливаем минимальные ENV переменные для тестов перед любыми импортами
# ВАЖНО: setdefault НЕ переопределяет уже установленные переменные,
# что позволяет запускать интеграционные тесты с реальной БД через pytest
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('FERNET_ENCRYPTION_KEY', 'test_fernet_key_32_bytes_long!!')
os.environ.setdefault('JWT_SECRET_KEY', 'test_jwt_secret_key')
os.environ.setdefault('USE_DATABASE', 'false')

try:
    import rarfile  # type: ignore
except Exception:  # pragma: no cover
    rarfile = None


@pytest.fixture
def ensure_env():
    has_tesseract = shutil.which("tesseract") is not None
    has_unrar = shutil.which("unrar") is not None
    return {"tesseract": has_tesseract, "unrar": has_unrar}


@pytest.fixture
def make_txt(tmp_path: Path):
    def _make_txt(name: str, text: str, encoding: str = "utf-8") -> Path:
        p = tmp_path / name
        p.write_text(text, encoding=encoding, errors="ignore")
        return p
    return _make_txt


@pytest.fixture
def make_docx(tmp_path: Path):
    def _make_docx(name: str, paragraphs: Optional[List[str]] = None) -> Path:
        try:
            from docx import Document  # type: ignore
        except Exception:  # pragma: no cover
            pytest.skip("python-docx not available")
        p = tmp_path / name
        d = Document()
        for t in (paragraphs or ["тест"]):
            d.add_paragraph(t)
        d.save(p)
        return p
    return _make_docx


@pytest.fixture
def make_xlsx(tmp_path: Path):
    def _make_xlsx(name: str, cells: Optional[List[Tuple[int, int, str]]] = None) -> Path:
        try:
            import openpyxl  # type: ignore
        except Exception:  # pragma: no cover
            pytest.skip("openpyxl not available")
        p = tmp_path / name
        wb = openpyxl.Workbook()
        ws = wb.active
        for r, c, v in (cells or [(1, 1, "шахматы")]):
            ws.cell(row=r, column=c, value=v)
        wb.save(p)
        return p
    return _make_xlsx


@pytest.fixture
def make_zip(tmp_path: Path):
    def _make_zip(name: str, files: dict[str, bytes]) -> Path:
        z = tmp_path / name
        with zipfile.ZipFile(z, "w") as zf:
            for arcname, data in files.items():
                zf.writestr(arcname, data)
        return z
    return _make_zip


@pytest.fixture
def make_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    return root


@pytest.fixture
def client():
    """Flask test client для тестов endpoints."""
    from webapp import create_app
    
    app = create_app()
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client
