"""Утилиты для работы с виртуальными путями архивов."""
import os
import zipfile
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class ArchiveEntry:
    """Элемент архива или виртуальной папки."""
    name: str  # Имя файла/папки
    path: str  # Полный виртуальный путь
    is_archive: bool  # True если это архив
    is_virtual_folder: bool  # True если это виртуальная папка внутри архива
    size: int = 0
    status: str = 'ok'  # ok, error, unsupported
    error: Optional[str] = None


def parse_virtual_path(path: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """
    Разбирает виртуальный путь архива.
    
    Args:
        path: Путь вида 'zip://a.zip!/nested/file.txt' или 'uploads/file.txt'
        
    Returns:
        Tuple[scheme, segments] где:
        - scheme: 'zip', 'rar' или None (для обычных файлов)
        - segments: список (archive_path, inner_path) для каждого уровня вложенности
        
    Examples:
        'zip://a.zip!/doc.txt' -> ('zip', [('a.zip', 'doc.txt')])
        'zip://outer.zip!/inner.zip!/doc.txt' -> ('zip', [('outer.zip', 'inner.zip'), ('inner.zip', 'doc.txt')])
        'file.txt' -> (None, [])
    """
    if '://' not in path:
        return None, []
    
    scheme, rest = path.split('://', 1)
    if scheme not in ('zip', 'rar'):
        return None, []
    
    # Разбиваем по !/ для извлечения уровней вложенности
    parts = rest.split('!/')
    if len(parts) < 2:
        return None, []
    
    segments = []
    for i in range(len(parts) - 1):
        archive = parts[i] if i == 0 else parts[i].rsplit('/', 1)[-1]
        inner = parts[i + 1] if i + 1 < len(parts) - 1 else parts[-1]
        segments.append((archive, inner))
    
    return scheme, segments


def is_archive_path(path: str) -> bool:
    """Проверяет, является ли путь виртуальным путём архива."""
    return '://' in path and any(path.startswith(p) for p in ('zip://', 'rar://'))


def get_archive_root(path: str) -> Optional[str]:
    """
    Извлекает корневой архив из виртуального пути.
    
    Args:
        path: Виртуальный путь
        
    Returns:
        Путь к корневому архиву или None
        
    Example:
        'zip://a.zip!/nested/file.txt' -> 'a.zip'
    """
    scheme, segments = parse_virtual_path(path)
    if not segments:
        return None
    return segments[0][0]


def list_archive_contents(archive_path: str, base_dir: str) -> List[ArchiveEntry]:
    """
    Получает список содержимого архива с группировкой по виртуальным папкам.
    
    Args:
        archive_path: Относительный путь к архиву от base_dir
        base_dir: Базовая директория (обычно UPLOAD_FOLDER)
        
    Returns:
        Список ArchiveEntry для файлов и виртуальных папок внутри архива
    """
    full_path = os.path.join(base_dir, archive_path)
    if not os.path.exists(full_path):
        return []
    
    ext = archive_path.rsplit('.', 1)[-1].lower() if '.' in archive_path else ''
    entries: List[ArchiveEntry] = []
    virtual_folders: Dict[str, ArchiveEntry] = {}
    
    try:
        if ext == 'zip':
            with zipfile.ZipFile(full_path, 'r') as z:
                for info in z.infolist():
                    inner_path = info.filename
                    
                    # Пропускаем директории (они уже представлены через файлы)
                    if info.is_dir():
                        continue
                    
                    # Определяем, в какой виртуальной папке находится файл
                    if '/' in inner_path:
                        folder_path = inner_path.rsplit('/', 1)[0]
                        folder_key = f"zip://{archive_path}!/{folder_path}"
                        
                        if folder_key not in virtual_folders:
                            virtual_folders[folder_key] = ArchiveEntry(
                                name=folder_path.split('/')[-1],
                                path=folder_key,
                                is_archive=False,
                                is_virtual_folder=True
                            )
                    
                    # Добавляем файл
                    file_ext = inner_path.rsplit('.', 1)[-1].lower() if '.' in inner_path else ''
                    is_nested_archive = file_ext in ('zip', 'rar')
                    
                    entries.append(ArchiveEntry(
                        name=inner_path.split('/')[-1],
                        path=f"zip://{archive_path}!/{inner_path}",
                        is_archive=is_nested_archive,
                        is_virtual_folder=False,
                        size=info.file_size
                    ))
        elif ext == 'rar':
            try:
                import rarfile  # type: ignore
                with rarfile.RarFile(full_path, 'r') as rf:
                    for info in rf.infolist():
                        inner_path = info.filename
                        
                        if info.isdir():
                            continue
                        
                        if '/' in inner_path:
                            folder_path = inner_path.rsplit('/', 1)[0]
                            folder_key = f"rar://{archive_path}!/{folder_path}"
                            
                            if folder_key not in virtual_folders:
                                virtual_folders[folder_key] = ArchiveEntry(
                                    name=folder_path.split('/')[-1],
                                    path=folder_key,
                                    is_archive=False,
                                    is_virtual_folder=True
                                )
                        
                        file_ext = inner_path.rsplit('.', 1)[-1].lower() if '.' in inner_path else ''
                        is_nested_archive = file_ext in ('zip', 'rar')
                        
                        entries.append(ArchiveEntry(
                            name=inner_path.split('/')[-1],
                            path=f"rar://{archive_path}!/{inner_path}",
                            is_archive=is_nested_archive,
                            is_virtual_folder=False,
                            size=info.file_size
                        ))
            except Exception as e:
                # RAR не поддержан или ошибка
                return [ArchiveEntry(
                    name=os.path.basename(archive_path),
                    path=archive_path,
                    is_archive=True,
                    is_virtual_folder=False,
                    status='error',
                    error=f'RAR не поддержан или ошибка: {str(e)}'
                )]
    except zipfile.BadZipFile:
        return [ArchiveEntry(
            name=os.path.basename(archive_path),
            path=archive_path,
            is_archive=True,
            is_virtual_folder=False,
            status='error',
            error='Повреждённый ZIP архив'
        )]
    except Exception as e:
        return [ArchiveEntry(
            name=os.path.basename(archive_path),
            path=archive_path,
            is_archive=True,
            is_virtual_folder=False,
            status='error',
            error=str(e)
        )]
    
    # Объединяем виртуальные папки и файлы
    return list(virtual_folders.values()) + entries


def sanitize_archive_path(archive_path: str) -> str:
    """
    Очищает путь от небезопасных компонентов (защита от ZipSlip).
    
    Args:
        archive_path: Путь внутри архива
        
    Returns:
        Безопасный путь
    """
    # Нормализуем путь
    normalized = os.path.normpath(archive_path)
    
    # Убираем абсолютные пути
    if os.path.isabs(normalized):
        normalized = normalized.lstrip(os.sep)
    
    # Убираем попытки обхода директорий
    parts = normalized.split(os.sep)
    safe_parts = [p for p in parts if p and p != '..' and p != '.']
    
    return os.path.join(*safe_parts) if safe_parts else ''
