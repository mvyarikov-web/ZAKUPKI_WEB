"""
Тесты для модуля нормализации путей.

Проверяет корректность работы функций из webapp/utils/path_utils.py
для обеспечения единообразия путей между БД, файловой системой и UI.
"""
import os
import pytest
from webapp.utils.path_utils import normalize_path, get_relative_path, paths_match


class TestNormalizePath:
    """Тесты функции normalize_path."""
    
    def test_forward_slashes(self):
        """Пути с forward slashes остаются без изменений."""
        assert normalize_path('folder/file.txt') == 'folder/file.txt'
        assert normalize_path('a/b/c/file.pdf') == 'a/b/c/file.pdf'
    
    def test_backslashes_to_forward(self):
        """Backslashes преобразуются в forward slashes."""
        assert normalize_path('folder\\file.txt') == 'folder/file.txt'
        assert normalize_path('a\\b\\c\\file.pdf') == 'a/b/c/file.pdf'
    
    def test_mixed_slashes(self):
        """Смешанные слэши нормализуются."""
        assert normalize_path('folder\\sub/file.txt') == 'folder/sub/file.txt'
        assert normalize_path('a/b\\c/file.pdf') == 'a/b/c/file.pdf'
    
    def test_double_slashes_removed(self):
        """Двойные слэши убираются."""
        assert normalize_path('folder//file.txt') == 'folder/file.txt'
        assert normalize_path('a///b/file.pdf') == 'a/b/file.pdf'
    
    def test_leading_slash_removed(self):
        """Начальный слэш убирается (пути относительные)."""
        assert normalize_path('/folder/file.txt') == 'folder/file.txt'
        assert normalize_path('/a/b/c/file.pdf') == 'a/b/c/file.pdf'
    
    def test_empty_path(self):
        """Пустой путь остаётся пустым."""
        assert normalize_path('') == ''
        assert normalize_path(None) is None
    
    def test_single_file(self):
        """Имя файла без папок."""
        assert normalize_path('file.txt') == 'file.txt'
        assert normalize_path('document.pdf') == 'document.pdf'


class TestGetRelativePath:
    """Тесты функции get_relative_path."""
    
    def test_relative_path_basic(self, tmp_path):
        """Базовый случай: файл внутри базовой папки."""
        base = tmp_path / "uploads"
        base.mkdir()
        file_path = base / "test.txt"
        file_path.write_text("test")
        
        rel_path = get_relative_path(str(file_path), str(base))
        assert rel_path == 'test.txt'
    
    def test_relative_path_nested(self, tmp_path):
        """Файл во вложенной папке."""
        base = tmp_path / "uploads"
        base.mkdir()
        subfolder = base / "documents"
        subfolder.mkdir()
        file_path = subfolder / "test.pdf"
        file_path.write_text("test")
        
        rel_path = get_relative_path(str(file_path), str(base))
        assert rel_path == 'documents/test.pdf'
    
    def test_relative_path_outside_base(self, tmp_path):
        """Файл вне базовой папки - возвращается только имя."""
        base = tmp_path / "uploads"
        base.mkdir()
        outside = tmp_path / "other" / "test.txt"
        outside.parent.mkdir(parents=True)
        outside.write_text("test")
        
        rel_path = get_relative_path(str(outside), str(base))
        assert rel_path == 'test.txt'
    
    def test_relative_path_normalization(self, tmp_path):
        """Путь нормализуется (forward slashes)."""
        base = tmp_path / "uploads"
        base.mkdir()
        subfolder = base / "documents"
        subfolder.mkdir()
        file_path = subfolder / "test.pdf"
        file_path.write_text("test")
        
        # На Windows путь может содержать backslashes
        rel_path = get_relative_path(str(file_path), str(base))
        # После нормализации должны быть forward slashes
        assert '\\' not in rel_path
        assert rel_path == 'documents/test.pdf'


class TestPathsMatch:
    """Тесты функции paths_match."""
    
    def test_identical_paths(self):
        """Идентичные пути совпадают."""
        assert paths_match('folder/file.txt', 'folder/file.txt')
        assert paths_match('a/b/c.pdf', 'a/b/c.pdf')
    
    def test_backslash_vs_forward(self):
        """Пути с разными типами слэшей совпадают после нормализации."""
        assert paths_match('folder\\file.txt', 'folder/file.txt')
        assert paths_match('a\\b\\c.pdf', 'a/b/c.pdf')
    
    def test_with_leading_slash(self):
        """Пути с и без начального слэша совпадают."""
        assert paths_match('/folder/file.txt', 'folder/file.txt')
        assert paths_match('folder/file.txt', '/folder/file.txt')
    
    def test_different_paths(self):
        """Разные пути не совпадают."""
        assert not paths_match('folder/file1.txt', 'folder/file2.txt')
        assert not paths_match('a/b/c.pdf', 'x/y/z.pdf')
    
    def test_case_sensitive(self):
        """Сравнение чувствительно к регистру."""
        # На большинстве систем пути чувствительны к регистру
        assert not paths_match('Folder/File.txt', 'folder/file.txt')


class TestIntegrationScenarios:
    """Интеграционные тесты реальных сценариев."""
    
    def test_db_to_ui_path_matching(self):
        """Путь из БД должен совпадать с путём из UI после нормализации."""
        # Сценарий: путь сохранён в БД с backslashes (Windows)
        db_path = 'documents\\contracts\\contract.pdf'
        # UI всегда использует forward slashes
        ui_path = 'documents/contracts/contract.pdf'
        
        # Нормализация обеспечивает совпадение
        assert normalize_path(db_path) == normalize_path(ui_path)
        assert paths_match(db_path, ui_path)
    
    def test_search_result_to_file_list_matching(self):
        """Результат поиска должен находить файл в списке."""
        # Путь из результата поиска (user_path из БД)
        search_result_path = normalize_path('folder\\subfolder\\document.txt')
        
        # Список файлов из /files_json
        files = [
            {'path': normalize_path('folder/subfolder/document.txt')},
            {'path': normalize_path('folder/other.txt')},
        ]
        
        # Должны найти совпадение
        matched = any(paths_match(search_result_path, f['path']) for f in files)
        assert matched
    
    def test_view_endpoint_path_resolution(self, tmp_path):
        """Путь из URL /view должен найти документ в БД."""
        # Симулируем структуру
        base = tmp_path / "uploads"
        base.mkdir()
        subfolder = base / "reports"
        subfolder.mkdir()
        file_path = subfolder / "report.pdf"
        file_path.write_text("test")
        
        # URL path (может содержать encoded слэши)
        url_path = 'reports/report.pdf'
        
        # user_path в БД (сохранён через get_relative_path)
        db_user_path = get_relative_path(str(file_path), str(base))
        
        # После нормализации должны совпадать
        assert paths_match(url_path, db_user_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
