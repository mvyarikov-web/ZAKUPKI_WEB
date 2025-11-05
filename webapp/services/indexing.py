"""Сервис для работы с индексацией и поиском."""
import os
from flask import current_app
from document_processor import DocumentProcessor


def parse_index_char_counts(index_path: str) -> dict:
    """Парсит _search_index.txt и возвращает {relative_path: char_count} для всех файлов, включая файлы из архивов.
    
    Безопасен к ошибкам формата; игнорирует записи без чисел.
    
    Args:
        index_path: Путь к индексному файлу
        
    Returns:
        Словарь {путь_к_файлу: количество_символов}
    """
    mapping: dict[str, int] = {}
    if not os.path.exists(index_path):
        return mapping
    
    try:
        current_title = None
        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw in f:
                line = raw.strip()
                if line.startswith('ЗАГОЛОВОК:'):
                    title = line.split(':', 1)[1].strip()
                    # Теперь обрабатываем все файлы, включая из архивов
                    if title:
                        current_title = title
                    else:
                        current_title = None
                elif current_title and line.startswith('Формат:') and 'Символов:' in line:
                    try:
                        # ожидание шаблона: Формат: ... | Символов: N | ...
                        parts = [p.strip() for p in line.split('|')]
                        for p in parts:
                            if p.startswith('Символов:'):
                                n_str = p.split(':', 1)[1].strip()
                                n = int(''.join(ch for ch in n_str if ch.isdigit())) if n_str else 0
                                mapping[current_title] = n
                                break
                    except Exception:
                        # пропускаем некорректные строки
                        pass
                elif line.startswith('====='):
                    # разделитель — сбрасываем состояние
                    current_title = None
    except Exception:
        current_app.logger.exception('Ошибка парсинга индекса для char_count')
    
    return mapping


def build_search_index(uploads_folder: str, index_folder: str):
    """Строит поисковый индекс для файлов в папке uploads.
    
    Args:
        uploads_folder: Папка с файлами для индексации
        index_folder: Папка для сохранения индекса
        
    Returns:
        tuple: (success: bool, message: str, char_counts: dict)
    """
    try:
        os.makedirs(index_folder, exist_ok=True)
        
        processor = DocumentProcessor()
        index_path = processor.create_search_index(uploads_folder)
        
        # Парсим char_count для каждого файла
        char_counts = parse_index_char_counts(index_path)
        
        current_app.logger.info(f'Индекс построен: {index_path}, файлов: {len(char_counts)}')
        return True, 'Индекс успешно построен', char_counts
        
    except Exception as e:
        current_app.logger.exception('Ошибка построения индекса')
        return False, str(e), {}


def search_in_index(index_path: str, keywords: list, context: int = 80):
    """Выполняет поиск по индексу.
    
    Args:
        index_path: Путь к индексному файлу
        keywords: Список ключевых слов для поиска
        context: Размер контекста вокруг найденного слова
        
    Returns:
        list: Список результатов поиска
    """
    try:
        processor = DocumentProcessor()
        results = processor.search_keywords(index_path, keywords, context=context)
        return results
    except Exception:
        current_app.logger.exception('Ошибка поиска')
        raise


def get_index_path(index_folder: str) -> str:
    """Возвращает путь к файлу индекса.
    
    Args:
        index_folder: Папка с индексом
        
    Returns:
        Полный путь к индексному файлу
    """
    return os.path.join(index_folder, '_search_index.txt')
