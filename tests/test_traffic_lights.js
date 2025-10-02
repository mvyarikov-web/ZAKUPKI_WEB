/**
 * Тесты для JavaScript логики светофоров.
 * Запуск: node tests/test_traffic_lights.js
 */

// Загружаем модуль светофоров
const {
    getFileTrafficLightColor,
    getFolderTrafficLightColor,
    isFileIndexed,
    getTrafficLightSortPriority,
    TRAFFIC_LIGHT_COLORS,
    FILE_STATUSES
} = require('../static/js/traffic-lights.js');

// Цвета для удобства
const { RED, YELLOW, GREEN, GRAY } = TRAFFIC_LIGHT_COLORS;
const { ERROR, UNSUPPORTED, CONTAINS_KEYWORDS, NO_KEYWORDS, PROCESSING, NOT_CHECKED } = FILE_STATUSES;

// Простой фреймворк для тестирования
let testsPassed = 0;
let testsFailed = 0;

function assert(condition, message) {
    if (condition) {
        testsPassed++;
    } else {
        testsFailed++;
        console.error(`❌ FAILED: ${message}`);
    }
}

function assertEqual(actual, expected, message) {
    if (actual === expected) {
        testsPassed++;
    } else {
        testsFailed++;
        console.error(`❌ FAILED: ${message}`);
        console.error(`   Expected: ${expected}`);
        console.error(`   Actual:   ${actual}`);
    }
}

function describe(name, fn) {
    console.log(`\n📋 ${name}`);
    fn();
}

// Тесты для файлов
describe('Тесты светофоров для файлов', () => {
    
    // Тест 1: Неиндексированные файлы всегда красные
    describe('  🔴 Неиндексированный файл всегда красный', () => {
        assertEqual(getFileTrafficLightColor(ERROR, 100, false, false), RED, 
            'Error файл до поиска должен быть красным');
        assertEqual(getFileTrafficLightColor(ERROR, 100, false, true), RED, 
            'Error файл после поиска без результатов должен быть красным');
        assertEqual(getFileTrafficLightColor(ERROR, 100, true, true), RED, 
            'Error файл после поиска с результатами должен быть красным');
        
        assertEqual(getFileTrafficLightColor(UNSUPPORTED, 50, false, false), RED, 
            'Unsupported файл до поиска должен быть красным');
        assertEqual(getFileTrafficLightColor(UNSUPPORTED, 50, false, true), RED, 
            'Unsupported файл после поиска без результатов должен быть красным');
        assertEqual(getFileTrafficLightColor(UNSUPPORTED, 50, true, true), RED, 
            'Unsupported файл после поиска с результатами должен быть красным');
        
        assertEqual(getFileTrafficLightColor(PROCESSING, 0, false, false), RED, 
            'Файл с нулевым char_count до поиска должен быть красным');
        assertEqual(getFileTrafficLightColor(PROCESSING, 0, false, true), RED, 
            'Файл с нулевым char_count после поиска без результатов должен быть красным');
        assertEqual(getFileTrafficLightColor(PROCESSING, 0, true, true), RED, 
            'Файл с нулевым char_count после поиска с результатами должен быть красным');
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 0, true, true), RED, 
            'Contains_keywords с нулевым char_count должен быть красным');
    });
    
    // Тест 2: Проиндексированные файлы до поиска - серые
    describe('  ⚪ Проиндексированный файл до поиска - серый', () => {
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, false, false), GRAY, 
            'Contains_keywords до поиска должен быть серым');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, false, false), GRAY, 
            'No_keywords до поиска должен быть серым');
        assertEqual(getFileTrafficLightColor(PROCESSING, 200, false, false), GRAY, 
            'Processing до поиска должен быть серым');
        assertEqual(getFileTrafficLightColor(NOT_CHECKED, null, false, false), GRAY, 
            'Not_checked до поиска должен быть серым');
    });
    
    // Тест 3: Проиндексированные файлы с совпадениями - зелёные
    describe('  🟢 Проиндексированный файл с совпадениями - зелёный', () => {
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, true, true), GREEN, 
            'Contains_keywords с результатами должен быть зелёным');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, true, true), GREEN, 
            'No_keywords с результатами должен быть зелёным');
        assertEqual(getFileTrafficLightColor(PROCESSING, 200, true, true), GREEN, 
            'Processing с результатами должен быть зелёным');
    });
    
    // Тест 4: Проиндексированные файлы без совпадений - жёлтые
    describe('  🟡 Проиндексированный файл без совпадений - жёлтый', () => {
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, false, true), YELLOW, 
            'Contains_keywords без результатов должен быть жёлтым');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, false, true), YELLOW, 
            'No_keywords без результатов должен быть жёлтым');
        assertEqual(getFileTrafficLightColor(PROCESSING, 200, false, true), YELLOW, 
            'Processing без результатов должен быть жёлтым');
    });
});

// Тесты для проверки индексации
describe('Тесты проверки индексации файлов', () => {
    // Проиндексированные
    assert(isFileIndexed(CONTAINS_KEYWORDS, 100) === true, 'Contains_keywords с char_count > 0 проиндексирован');
    assert(isFileIndexed(NO_KEYWORDS, 50) === true, 'No_keywords с char_count > 0 проиндексирован');
    assert(isFileIndexed(PROCESSING, 200) === true, 'Processing с char_count > 0 проиндексирован');
    
    // Неиндексированные
    assert(isFileIndexed(ERROR, 100) === false, 'Error не проиндексирован');
    assert(isFileIndexed(UNSUPPORTED, 50) === false, 'Unsupported не проиндексирован');
    assert(isFileIndexed(PROCESSING, 0) === false, 'Processing с char_count = 0 не проиндексирован');
});

// Тесты для папок
describe('Тесты светофоров для папок', () => {
    
    // Тест 1: Папка с зелёными файлами - зелёная (наивысший приоритет)
    describe('  🟢 Папка с файлами с совпадениями - зелёная', () => {
        assertEqual(getFolderTrafficLightColor([GREEN, YELLOW, GRAY]), GREEN, 
            'Папка [green, yellow, gray] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([GREEN, YELLOW]), GREEN, 
            'Папка [green, yellow] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([GREEN, GRAY]), GREEN, 
            'Папка [green, gray] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([GREEN]), GREEN, 
            'Папка [green] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([GREEN, GREEN, YELLOW]), GREEN, 
            'Папка [green, green, yellow] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([GREEN, GREEN, GREEN]), GREEN, 
            'Папка [green, green, green] должна быть зелёной');
        // Зелёный имеет приоритет даже при наличии красных файлов
        assertEqual(getFolderTrafficLightColor([RED, GREEN]), GREEN, 
            'Папка [red, green] должна быть зелёной (зелёный приоритетнее)');
        assertEqual(getFolderTrafficLightColor([RED, GREEN, YELLOW, GRAY]), GREEN, 
            'Папка [red, green, yellow, gray] должна быть зелёной');
        assertEqual(getFolderTrafficLightColor([RED, RED, GREEN]), GREEN, 
            'Папка [red, red, green] должна быть зелёной');
    });
    
    // Тест 2: Папка с жёлтыми файлами - жёлтая (при отсутствии зелёных)
    describe('  🟡 Папка с проиндексированными файлами без совпадений - жёлтая', () => {
        assertEqual(getFolderTrafficLightColor([YELLOW, GRAY]), YELLOW, 
            'Папка [yellow, gray] должна быть жёлтой');
        assertEqual(getFolderTrafficLightColor([YELLOW]), YELLOW, 
            'Папка [yellow] должна быть жёлтой');
        assertEqual(getFolderTrafficLightColor([YELLOW, YELLOW, GRAY]), YELLOW, 
            'Папка [yellow, yellow, gray] должна быть жёлтой');
        assertEqual(getFolderTrafficLightColor([YELLOW, YELLOW, YELLOW]), YELLOW, 
            'Папка [yellow, yellow, yellow] должна быть жёлтой');
        // Жёлтый имеет приоритет над красным и серым
        assertEqual(getFolderTrafficLightColor([RED, YELLOW]), YELLOW, 
            'Папка [red, yellow] должна быть жёлтой (жёлтый приоритетнее красного)');
        assertEqual(getFolderTrafficLightColor([RED, YELLOW, GRAY]), YELLOW, 
            'Папка [red, yellow, gray] должна быть жёлтой');
    });
    
    // Тест 3: Папка с ТОЛЬКО красными файлами - красная
    describe('  🔴 Папка с ТОЛЬКО неиндексированными файлами - красная', () => {
        assertEqual(getFolderTrafficLightColor([RED]), RED, 
            'Папка [red] должна быть красной');
        assertEqual(getFolderTrafficLightColor([RED, RED, RED]), RED, 
            'Папка [red, red, red] должна быть красной (все файлы не проиндексированы)');
    });
    
    // Тест 4: Папка только с серыми файлами - серая
    describe('  ⚪ Папка только с серыми файлами - серая', () => {
        assertEqual(getFolderTrafficLightColor([GRAY]), GRAY, 
            'Папка [gray] должна быть серой');
        assertEqual(getFolderTrafficLightColor([GRAY, GRAY]), GRAY, 
            'Папка [gray, gray] должна быть серой');
        assertEqual(getFolderTrafficLightColor([GRAY, GRAY, GRAY]), GRAY, 
            'Папка [gray, gray, gray] должна быть серой');
        // Смесь серых и красных без жёлтых/зелёных - серая
        assertEqual(getFolderTrafficLightColor([RED, GRAY]), GRAY, 
            'Папка [red, gray] должна быть серой (смесь без проиндексированных с результатами)');
    });
    
    // Тест 5: Пустая папка - серая
    describe('  Пустая папка - серая', () => {
        assertEqual(getFolderTrafficLightColor([]), GRAY, 
            'Пустая папка должна быть серой');
        assertEqual(getFolderTrafficLightColor(null), GRAY, 
            'Папка с null должна быть серой');
    });
});

// Тесты приоритета цветов для папок
describe('Тесты приоритета цветов для папок', () => {
    assertEqual(getFolderTrafficLightColor([RED, GREEN, YELLOW, GRAY]), GREEN, 
        'Приоритет 1: Зелёный > все остальные');
    assertEqual(getFolderTrafficLightColor([RED, YELLOW, GRAY]), YELLOW, 
        'Приоритет 2: Жёлтый > красный и серый');
    assertEqual(getFolderTrafficLightColor([RED, RED, RED]), RED, 
        'Приоритет 3: Красный (только когда ВСЕ файлы красные)');
    assertEqual(getFolderTrafficLightColor([GRAY, GRAY]), GRAY, 
        'Приоритет 4: Серый (только при отсутствии остальных)');
});

// Тесты сортировки
describe('Тесты приоритета сортировки', () => {
    assertEqual(getTrafficLightSortPriority(GREEN), 3, 
        'Зелёный приоритет = 3');
    assertEqual(getTrafficLightSortPriority(GRAY), 2, 
        'Серый приоритет = 2');
    assertEqual(getTrafficLightSortPriority(YELLOW), 2, 
        'Жёлтый приоритет = 2');
    assertEqual(getTrafficLightSortPriority(RED), 1, 
        'Красный приоритет = 1');
    
    // Тест сортировки
    const colors = [RED, YELLOW, GREEN, GRAY];
    const sorted = colors.sort((a, b) => getTrafficLightSortPriority(b) - getTrafficLightSortPriority(a));
    assertEqual(sorted[0], GREEN, 'Зелёный должен быть первым при сортировке');
    assertEqual(sorted[sorted.length - 1], RED, 'Красный должен быть последним при сортировке');
});

// Тесты специфичных сценариев
describe('Тесты специфичных сценариев', () => {
    
    describe('  До первого поиска', () => {
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, false, false), GRAY, 
            'Проиндексированные файлы - серые');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, false, false), GRAY, 
            'Проиндексированные файлы - серые');
        assertEqual(getFileTrafficLightColor(ERROR, 100, false, false), RED, 
            'Неиндексированные файлы - красные');
        assertEqual(getFileTrafficLightColor(UNSUPPORTED, 50, false, false), RED, 
            'Неиндексированные файлы - красные');
    });
    
    describe('  После поиска', () => {
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, true, true), GREEN, 
            'С совпадениями = зелёный');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, false, true), YELLOW, 
            'Без совпадений = жёлтый');
        assertEqual(getFileTrafficLightColor(ERROR, 100, true, true), RED, 
            'Неиндексированные остаются красными');
        assertEqual(getFileTrafficLightColor(UNSUPPORTED, 50, true, true), RED, 
            'Неиндексированные остаются красными');
    });
    
    describe('  Обратный поиск (exclude mode)', () => {
        // Логика определения совпадений обрабатывается на уровне поиска
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 100, true, true), GREEN, 
            'Файл НЕ содержит слова = совпадение = зелёный');
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, false, true), YELLOW, 
            'Файл содержит слова = не совпадение = жёлтый');
    });
    
    describe('  Файлы в архивах', () => {
        assertEqual(getFileTrafficLightColor(ERROR, 100, false, false), RED, 
            'Неиндексированный файл в архиве - красный');
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, false, false), GRAY, 
            'Проиндексированный файл в архиве до поиска - серый');
        assertEqual(getFileTrafficLightColor(CONTAINS_KEYWORDS, 100, true, true), GREEN, 
            'Проиндексированный файл в архиве с совпадениями - зелёный');
        assertEqual(getFileTrafficLightColor(NO_KEYWORDS, 50, false, true), YELLOW, 
            'Проиндексированный файл в архиве без совпадений - жёлтый');
        
        // Архив как папка
        assertEqual(getFolderTrafficLightColor([RED, RED, RED]), RED, 
            'Архив с ТОЛЬКО красными файлами - красный');
        assertEqual(getFolderTrafficLightColor([RED, GREEN]), GREEN, 
            'Архив с зелёными файлами - зелёный (зелёный приоритетнее)');
        assertEqual(getFolderTrafficLightColor([GREEN, YELLOW]), GREEN, 
            'Архив с зелёными файлами - зелёный');
        assertEqual(getFolderTrafficLightColor([YELLOW, GRAY]), YELLOW, 
            'Архив с жёлтыми файлами - жёлтый');
        assertEqual(getFolderTrafficLightColor([GRAY, GRAY]), GRAY, 
            'Архив с серыми файлами - серый');
    });
});

// Итоги
console.log('\n' + '='.repeat(60));
if (testsFailed === 0) {
    console.log(`✅ Все тесты пройдены успешно! (${testsPassed} тестов)`);
    process.exit(0);
} else {
    console.log(`❌ Некоторые тесты провалились:`);
    console.log(`   Пройдено: ${testsPassed}`);
    console.log(`   Провалено: ${testsFailed}`);
    process.exit(1);
}
