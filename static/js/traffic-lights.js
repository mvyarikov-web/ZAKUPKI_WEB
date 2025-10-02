/**
 * Модуль логики светофоров для клиентской части.
 * Централизованная логика определения цветов статусов в JavaScript.
 */

// Константы цветов
const TRAFFIC_LIGHT_COLORS = {
    RED: 'red',
    YELLOW: 'yellow',
    GREEN: 'green', 
    GRAY: 'gray'
};

// Статусы файлов
const FILE_STATUSES = {
    ERROR: 'error',
    UNSUPPORTED: 'unsupported',
    CONTAINS_KEYWORDS: 'contains_keywords',
    NO_KEYWORDS: 'no_keywords',
    PROCESSING: 'processing',
    NOT_CHECKED: 'not_checked'
};

/**
 * Определяет цвет светофора для файла.
 * 
 * @param {string} status - статус файла
 * @param {number|null} charCount - количество символов в файле
 * @param {boolean} hasSearchResults - есть ли результаты поиска для файла
 * @param {boolean} searchPerformed - выполнялся ли поиск
 * @returns {string} цвет светофора
 */
function getFileTrafficLightColor(status, charCount = null, hasSearchResults = false, searchPerformed = false) {
    // Красный: не проиндексированные файлы (всегда красный, независимо от поиска)
    if (status === FILE_STATUSES.ERROR || status === FILE_STATUSES.UNSUPPORTED || charCount === 0) {
        return TRAFFIC_LIGHT_COLORS.RED;
    }
    
    // Если поиск был выполнен
    if (searchPerformed) {
        if (hasSearchResults) {
            return TRAFFIC_LIGHT_COLORS.GREEN; // Зелёный: есть совпадения
        } else {
            return TRAFFIC_LIGHT_COLORS.YELLOW; // Жёлтый: нет совпадений, но файл проиндексирован
        }
    }

    // Серый: проиндексированные, но поиск не производился
    if (status === FILE_STATUSES.CONTAINS_KEYWORDS ||
        status === FILE_STATUSES.NO_KEYWORDS ||
        status === FILE_STATUSES.PROCESSING ||
        status === FILE_STATUSES.NOT_CHECKED) {
        return TRAFFIC_LIGHT_COLORS.GRAY;
    }

    return TRAFFIC_LIGHT_COLORS.GRAY; // По умолчанию серый
}

/**
 * Определяет цвет светофора для папки на основе цветов файлов внутри.
 * 
 * Логика папки (вторична, определяется после светофоров файлов):
 * 1. Зелёный - есть хотя бы один зелёный файл (с результатами поиска)
 * 2. Жёлтый - есть проиндексированные файлы, но ни один не подходит (есть жёлтые, нет зелёных)
 * 3. Красный - ВСЕ файлы не проиндексированы (все красные)
 * 4. Серый - все файлы серые (поиск не выполнялся)
 * 
 * @param {string[]} fileColors - массив цветов файлов в папке
 * @returns {string} цвет светофора папки
 */
function getFolderTrafficLightColor(fileColors) {
    if (!fileColors || fileColors.length === 0) {
        return TRAFFIC_LIGHT_COLORS.GRAY;
    }

    const hasRed = fileColors.includes(TRAFFIC_LIGHT_COLORS.RED);
    const hasGreen = fileColors.includes(TRAFFIC_LIGHT_COLORS.GREEN);
    const hasYellow = fileColors.includes(TRAFFIC_LIGHT_COLORS.YELLOW);
    const hasGray = fileColors.includes(TRAFFIC_LIGHT_COLORS.GRAY);
    
    // Приоритет: зелёный -> жёлтый -> красный -> серый
    // 1. Если есть хотя бы один зелёный файл - папка зелёная
    if (hasGreen) {
        return TRAFFIC_LIGHT_COLORS.GREEN;
    }
    
    // 2. Если есть жёлтые файлы (проиндексированные без совпадений) - папка жёлтая
    if (hasYellow) {
        return TRAFFIC_LIGHT_COLORS.YELLOW;
    }
    
    // 3. Если ВСЕ файлы красные (не проиндексированы) - папка красная
    const allRed = fileColors.every(color => color === TRAFFIC_LIGHT_COLORS.RED);
    if (allRed) {
        return TRAFFIC_LIGHT_COLORS.RED;
    }
    
    // 4. Иначе серая (все файлы серые или смесь серых и красных без жёлтых/зелёных)
    return TRAFFIC_LIGHT_COLORS.GRAY;
}

/**
 * Проверяет, проиндексирован ли файл.
 * 
 * @param {string} status - статус файла
 * @param {number|null} charCount - количество символов
 * @returns {boolean} true если файл проиндексирован
 */
function isFileIndexed(status, charCount = null) {
    if (status === FILE_STATUSES.ERROR || status === FILE_STATUSES.UNSUPPORTED) {
        return false;
    }
    if (charCount === 0) {
        return false;
    }
    return true;
}

/**
 * Возвращает приоритет для сортировки по цвету светофора.
 * Больше число = выше в списке.
 * 
 * @param {string} color - цвет светофора
 * @returns {number} приоритет сортировки
 */
function getTrafficLightSortPriority(color) {
    const priorityMap = {
        [TRAFFIC_LIGHT_COLORS.GREEN]: 3,   // Файлы с результатами наверх
        [TRAFFIC_LIGHT_COLORS.GRAY]: 2,    // Проиндексированные в середину
        [TRAFFIC_LIGHT_COLORS.YELLOW]: 2,  // Проиндексированные без результатов в середину
        [TRAFFIC_LIGHT_COLORS.RED]: 1      // Неиндексированные вниз
    };
    return priorityMap[color] || 1;
}

/**
 * Проверяет, выполнялся ли поиск (есть ли видимые результаты поиска).
 * 
 * @returns {boolean} true если поиск выполнялся
 */
function isSearchPerformed() {
    // Проверяем наличие контейнера результатов поиска
    const searchResults = document.getElementById('search-results');
    const hasSearchResultsDiv = searchResults && searchResults.style.display !== 'none' && 
                              searchResults.innerHTML.trim() !== '';
    
    // Проверяем наличие элементов с результатами поиска
    const visibleResults = document.querySelectorAll('.file-search-results[style*="display: block"], .file-search-results:not([style*="display: none"])');
    
    // Проверяем наличие атрибутов data-has-results
    const filesWithResults = document.querySelectorAll('[data-has-results="1"]');
    
    return hasSearchResultsDiv || visibleResults.length > 0 || filesWithResults.length > 0;
}

/**
 * Проверяет, есть ли результаты поиска для файла.
 * 
 * @param {string} filePath - путь к файлу
 * @returns {boolean} true если есть результаты
 */
function hasSearchResultsForFile(filePath) {
    // Метод 1: Проверяем атрибут data-has-results
    const fileWrapper = document.querySelector(`[data-file-path="${CSS.escape(filePath)}"]`);
    if (fileWrapper && fileWrapper.getAttribute('data-has-results') === '1') {
        return true;
    }
    
    // Метод 2: Проверяем наличие видимых результатов поиска
    const searchResultsInFile = fileWrapper ? fileWrapper.querySelectorAll('.file-search-results[style*="display: block"], .file-search-results:not([style*="display: none"])') : [];
    if (searchResultsInFile.length > 0) {
        return true;
    }
    
    // Метод 3: Проверяем по селектору для элементов с результатами
    const escapedPath = CSS.escape(filePath);
    const hasResults = document.querySelector(`[data-file-path="${escapedPath}"] .file-search-results[style*="display: block"]`) !== null;
    
    return hasResults;
}

// Экспорт для использования в основном коде
if (typeof window !== 'undefined') {
    // Браузерная среда - добавляем в глобальный объект
    window.TrafficLights = {
        getFileTrafficLightColor,
        getFolderTrafficLightColor,
        isFileIndexed,
        getTrafficLightSortPriority,
        isSearchPerformed,
        hasSearchResultsForFile,
        COLORS: TRAFFIC_LIGHT_COLORS,
        STATUSES: FILE_STATUSES
    };
}

// Экспорт для Node.js/тестирования
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getFileTrafficLightColor,
        getFolderTrafficLightColor,
        isFileIndexed,
        getTrafficLightSortPriority,
        isSearchPerformed,
        hasSearchResultsForFile,
        TRAFFIC_LIGHT_COLORS,
        FILE_STATUSES
    };
}