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
 * Логика согласно спецификации инкремента 11:
 * 1. Зеленый: есть хотя бы один файл с зеленым статусом (успешный поиск)
 * 2. Желтый: есть проиндексированные файлы без результатов поиска (желтые), нет зеленых
 * 3. Красный: все файлы не проиндексированы и был поиск
 * 4. Серый: до первого поиска или при сбросе поиска
 * 
 * @param {string[]} fileColors - массив цветов файлов в папке
 * @returns {string} цвет светофора папки
 */
function getFolderTrafficLightColor(fileColors) {
    if (!fileColors || fileColors.length === 0) {
        return TRAFFIC_LIGHT_COLORS.GRAY;
    }

    const hasGreen = fileColors.includes(TRAFFIC_LIGHT_COLORS.GREEN);
    const hasYellow = fileColors.includes(TRAFFIC_LIGHT_COLORS.YELLOW);
    const hasRed = fileColors.includes(TRAFFIC_LIGHT_COLORS.RED);
    const hasGray = fileColors.includes(TRAFFIC_LIGHT_COLORS.GRAY);

    // Логика папки согласно спецификации инкремента 11
    // 1. Зеленый: если есть хотя бы один файл с успешным результатом поиска
    if (hasGreen) {
        return TRAFFIC_LIGHT_COLORS.GREEN;
    }
    
    // 2. Желтый: если есть проиндексированные файлы без результатов поиска, но нет зеленых
    if (hasYellow) {
        return TRAFFIC_LIGHT_COLORS.YELLOW;
    }
    
    // 3. Красный: если все файлы не проиндексированы и был поиск
    if (hasRed && !hasGray && !hasYellow && !hasGreen) {
        return TRAFFIC_LIGHT_COLORS.RED;
    }
    
    // 4. Серый: по умолчанию (до первого поиска или смешанные состояния)
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
 * Проверяет, выполнялся ли поиск.
 * Использует глобальный флаг window.searchWasPerformed, который устанавливается при выполнении поиска.
 * 
 * @returns {boolean} true если поиск выполнялся
 */
function isSearchPerformed() {
    // Проверяем глобальный флаг (устанавливается при выполнении поиска)
    if (window.searchWasPerformed === true) {
        return true;
    }
    
    // Fallback: проверяем наличие видимых результатов поиска
    const visibleResults = document.querySelectorAll('.file-search-results[style*="display: block"]');
    if (visibleResults.length > 0) {
        return true;
    }
    
    // Проверяем наличие атрибутов data-has-results
    const filesWithResults = document.querySelectorAll('[data-has-results="1"]');
    if (filesWithResults.length > 0) {
        return true;
    }
    
    return false;
}

/**
 * Проверяет, есть ли результаты поиска для файла.
 * 
 * @param {string} filePath - путь к файлу
 * @returns {boolean} true если есть результаты
 */
function hasSearchResultsForFile(filePath) {
    // Метод 1: Проверяем атрибут data-has-results (самый надежный)
    const fileWrapper = document.querySelector(`[data-file-path="${CSS.escape(filePath)}"]`);
    if (fileWrapper && fileWrapper.getAttribute('data-has-results') === '1') {
        return true;
    }
    
    // Метод 2: Проверяем наличие видимых результатов поиска с содержимым
    if (fileWrapper) {
        const searchResults = fileWrapper.querySelector('.file-search-results[style*="display: block"]');
        if (searchResults && searchResults.innerHTML.trim() !== '') {
            // Проверяем, что есть реальные сниппеты или блоки результатов
            const hasSnippets = searchResults.querySelector('.per-term-block, .context-snippet, .found-terms');
            return hasSnippets !== null;
        }
    }
    
    return false;
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