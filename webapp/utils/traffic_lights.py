"""
Модуль для логики светофоров файлов и папок.
Централизованная логика определения цветов статусов.
"""


class TrafficLightLogic:
    """
    Класс для определения цветов светофоров файлов и папок.
    
    Логика светофоров:
    - Красный: не проиндексированные файлы (error, unsupported, char_count=0)
    - Желтый: проиндексированные без совпадений при поиске
    - Зеленый: проиндексированные с совпадениями при поиске  
    - Серый: проиндексированные без поиска
    """
    
    # Константы цветов
    RED = 'red'
    YELLOW = 'yellow' 
    GREEN = 'green'
    GRAY = 'gray'
    
    # Статусы файлов
    STATUS_ERROR = 'error'
    STATUS_UNSUPPORTED = 'unsupported'
    STATUS_CONTAINS_KEYWORDS = 'contains_keywords'
    STATUS_NO_KEYWORDS = 'no_keywords'
    STATUS_PROCESSING = 'processing'
    STATUS_NOT_CHECKED = 'not_checked'
    
    @classmethod
    def get_file_traffic_light_color(cls, status, char_count=None, has_search_results=False, search_performed=False):
        """
        Определяет цвет светофора для файла.
        
        Args:
            status: статус файла (error, unsupported, contains_keywords, etc.)
            char_count: количество символов в файле (None или число)
            has_search_results: есть ли результаты поиска для файла
            search_performed: выполнялся ли поиск
            
        Returns:
            str: цвет светофора ('red', 'yellow', 'green', 'gray')
        """
        # Красный: не проиндексированные файлы
        if status in [cls.STATUS_ERROR, cls.STATUS_UNSUPPORTED] or char_count == 0:
            return cls.RED
        
        # Если поиск был выполнен
        if search_performed:
            if has_search_results:
                return cls.GREEN  # Зелёный: есть совпадения
            else:
                return cls.YELLOW  # Жёлтый: нет совпадений, но файл проиндексирован
        
        # Серый: проиндексированные, но поиск не производился
        if status in [cls.STATUS_CONTAINS_KEYWORDS, cls.STATUS_NO_KEYWORDS, cls.STATUS_PROCESSING]:
            return cls.GRAY
        
        return cls.GRAY  # По умолчанию серый для not_checked
    
    @classmethod
    def get_folder_traffic_light_color(cls, file_colors):
        """
        Определяет цвет светофора для папки на основе цветов файлов внутри.
        
        Логика папки (вторична, определяется после светофоров файлов):
        1. Зелёный - есть хотя бы один зелёный файл (с результатами поиска)
        2. Жёлтый - есть проиндексированные файлы, но ни один не подходит (есть жёлтые, нет зелёных)
        3. Красный - ВСЕ файлы не проиндексированы (все красные)
        4. Серый - все файлы серые (поиск не выполнялся)
        
        Args:
            file_colors: список цветов файлов в папке
            
        Returns:
            str: цвет светофора папки
        """
        if not file_colors:
            return cls.GRAY
        
        has_red = cls.RED in file_colors
        has_green = cls.GREEN in file_colors  
        has_yellow = cls.YELLOW in file_colors
        has_gray = cls.GRAY in file_colors
        
        # Приоритет: зелёный -> жёлтый -> красный -> серый
        # 1. Если есть хотя бы один зелёный файл - папка зелёная
        if has_green:
            return cls.GREEN
        
        # 2. Если есть жёлтые файлы (проиндексированные без совпадений) - папка жёлтая
        if has_yellow:
            return cls.YELLOW
        
        # 3. Если ВСЕ файлы красные (не проиндексированы) - папка красная
        all_red = all(color == cls.RED for color in file_colors)
        if all_red:
            return cls.RED
        
        # 4. Иначе серая (все файлы серые или смесь серых и красных без жёлтых/зелёных)
        return cls.GRAY
    
    @classmethod
    def is_file_indexed(cls, status, char_count=None):
        """
        Проверяет, проиндексирован ли файл.
        
        Args:
            status: статус файла
            char_count: количество символов
            
        Returns:
            bool: True если файл проиндексирован
        """
        if status in [cls.STATUS_ERROR, cls.STATUS_UNSUPPORTED]:
            return False
        if char_count == 0:
            return False
        return True
    
    @classmethod
    def get_sort_priority(cls, color):
        """
        Возвращает приоритет для сортировки по цвету светофора.
        Больше число = выше в списке.
        
        Args:
            color: цвет светофора
            
        Returns:
            int: приоритет сортировки
        """
        priority_map = {
            cls.GREEN: 3,   # Файлы с результатами наверх
            cls.GRAY: 2,    # Проиндексированные в середину
            cls.YELLOW: 2,  # Проиндексированные без результатов в середину
            cls.RED: 1      # Неиндексированные вниз
        }
        return priority_map.get(color, 1)


def get_traffic_light_color_for_js(status, char_count=None, has_search_results=False, search_performed=False):
    """
    Функция-обёртка для использования в JavaScript через вызовы сервера.
    Дублирует логику TrafficLightLogic.get_file_traffic_light_color.
    """
    return TrafficLightLogic.get_file_traffic_light_color(
        status, char_count, has_search_results, search_performed
    )