"""
Утилиты для нормализации путей.

Обеспечивает единообразное представление путей между БД, файловой системой и UI.
Все пути хранятся и передаются с forward slashes (/) для кросс-платформенности.
"""
import os


def normalize_path(path: str) -> str:
    """
    Нормализует путь к единому формату (forward slashes).
    
    Args:
        path: Путь к файлу (может содержать backslashes на Windows)
        
    Returns:
        Нормализованный путь с forward slashes
        
    Examples:
        >>> normalize_path('folder\\file.txt')
        'folder/file.txt'
        >>> normalize_path('folder/file.txt')
        'folder/file.txt'
    """
    if not path:
        return path
    
    # Заменяем backslashes на forward slashes
    normalized = path.replace('\\', '/')
    
    # Убираем лишние слэши
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    
    # Убираем начальный слэш (пути должны быть относительными от uploads/)
    if normalized.startswith('/'):
        normalized = normalized[1:]
    
    return normalized


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Получает относительный путь от base_path к file_path с нормализацией.
    
    Args:
        file_path: Абсолютный или относительный путь к файлу
        base_path: Базовый путь (например, uploads/)
        
    Returns:
        Нормализованный относительный путь
    """
    try:
        abs_file = os.path.abspath(file_path)
        abs_base = os.path.abspath(base_path)
        
        # Проверяем, что файл внутри базового пути
        if os.path.commonpath([abs_file, abs_base]) != abs_base:
            # Файл вне базового пути - возвращаем только имя файла
            return normalize_path(os.path.basename(file_path))
        
        rel_path = os.path.relpath(abs_file, abs_base)
        return normalize_path(rel_path)
    except (ValueError, Exception):
        # Fallback: возвращаем имя файла
        return normalize_path(os.path.basename(file_path))


def paths_match(path1: str, path2: str) -> bool:
    """
    Проверяет, совпадают ли два пути после нормализации.
    
    Args:
        path1: Первый путь
        path2: Второй путь
        
    Returns:
        True если пути совпадают после нормализации
    """
    return normalize_path(path1) == normalize_path(path2)
