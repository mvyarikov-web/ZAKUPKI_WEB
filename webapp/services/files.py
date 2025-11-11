"""Сервис для работы с файлами."""
import os


def is_safe_subpath(base_dir: str, user_path: str) -> bool:
    """Проверяет, что путь user_path не содержит path traversal атак (.. и абсолютные пути).
    
    В PURE DB MODE: файлы не хранятся физически, но проверка нужна для безопасности user_path.
    
    Args:
        base_dir: Базовая директория (используется как логический корень)
        user_path: Пользовательский путь
        
    Returns:
        True, если путь безопасен
    """
    try:
        # Проверка на абсолютные пути
        if os.path.isabs(user_path):
            return False
        
        # Нормализуем путь и проверяем на обход через ..
        normalized = os.path.normpath(user_path)
        
        # Если после нормализации путь начинается с .. - это попытка обхода
        if normalized.startswith('..') or normalized.startswith(os.sep):
            return False
        
        return True
    except Exception:
        return False


def safe_filename(filename):
    """Создает безопасное имя файла, сохраняя кириллицу.
    
    Args:
        filename: Исходное имя файла
        
    Returns:
        Безопасное имя файла
    """
    # Разделяем имя файла и расширение
    name, ext = os.path.splitext(filename)
    
    # Заменяем опасные символы
    dangerous_chars = '<>:"/\\|?*'
    for char in dangerous_chars:
        name = name.replace(char, '_')
    
    # Убираем лишние пробелы и точки
    name = name.strip('. ')
    
    # Если имя стало пустым, даем базовое имя
    if not name:
        name = 'file'
    
    return name + ext


def allowed_file(filename, allowed_extensions):
    """Проверяет поддержку расширения и исключает временные файлы Office (~$*, $*).
    
    Args:
        filename: Имя файла
        allowed_extensions: Набор разрешенных расширений
        
    Returns:
        True, если файл разрешен
    """
    if not filename:
        return False
    base = os.path.basename(filename)
    if base.startswith('~$') or base.startswith('$'):
        return False
    return '.' in base and base.rsplit('.', 1)[1].lower() in allowed_extensions
