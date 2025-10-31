# Исправление выделения текста в жёлтых зонах оптимизатора

## Проблема

Выделение мышкой и снятие выделения работало только для обычного текста, но **НЕ работало** для жёлтых зон, изначально отмеченных оптимизатором (`.highlight-span`):

❌ Нельзя было выделить текст внутри жёлтой зоны
❌ Клик по жёлтой зоне не снимал подсветку
❌ Выделение мышкой не распознавало, что находится внутри подсветки

## Причина

1. **Обработчик кликов** работал только для `.user-highlight`, игнорируя `.highlight-span`
2. **Функция `toggleSelectionHighlight`** проверяла наличие подсветок только в содержимом выделения, но не проверяла родительские элементы
3. **Функция `removeHighlightFromRange`** удаляла только пользовательские подсветки, не трогая исходные

## Решение

### 1. Добавлена обработка кликов для обоих типов подсветок

```javascript
// Было: только .user-highlight
if (target.classList && target.classList.contains('user-highlight')) {
    // удалить подсветку
}

// Стало: оба типа
if (target.classList && target.classList.contains('user-highlight')) {
    // удалить пользовательскую подсветку
}

if (target.classList && target.classList.contains('highlight-span')) {
    // удалить исходную подсветку
}
```

### 2. Улучшена логика определения подсветок

Функция `toggleSelectionHighlight` теперь проверяет **три случая**:

#### a) Выделение содержит подсветку внутри себя
```javascript
const tempDiv = document.createElement('div');
tempDiv.appendChild(range.cloneContents());
let hasHighlight = tempDiv.querySelector('.user-highlight, .highlight-span') !== null;
```

#### b) Выделение находится ВНУТРИ подсветки (проверка родителей)
```javascript
let node = startContainer.nodeType === Node.TEXT_NODE ? startContainer.parentNode : startContainer;
while (node && node !== optimizeTextPreview) {
    if (node.classList && (node.classList.contains('highlight-span') || node.classList.contains('user-highlight'))) {
        hasHighlight = true;
        break;
    }
    node = node.parentNode;
}
```

Это критически важно для случаев, когда пользователь выделяет часть текста внутри жёлтой зоны.

#### c) Конец выделения внутри подсветки
Аналогичная проверка для `endContainer`.

### 3. Обновлена функция удаления подсветок

```javascript
function removeHighlightFromRange(range) {
    // Удаляем пользовательские подсветки
    const userHighlights = optimizeTextPreview.querySelectorAll('.user-highlight');
    userHighlights.forEach(hl => {
        if (range.intersectsNode(hl)) {
            const textNode = document.createTextNode(hl.textContent);
            hl.parentNode.replaceChild(textNode, hl);
        }
    });
    
    // Удаляем исходные подсветки оптимизатора
    const originalHighlights = optimizeTextPreview.querySelectorAll('.highlight-span');
    originalHighlights.forEach(hl => {
        if (range.intersectsNode(hl)) {
            const textNode = document.createTextNode(hl.textContent);
            hl.parentNode.replaceChild(textNode, hl);
        }
    });
}
```

### 4. Обновлены счётчики подсветок

Все места, где обновляется счётчик, теперь учитывают оба типа:
```javascript
highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span, .user-highlight'));
```

## Результат

✅ **Клик по жёлтой зоне** → подсветка исчезает (работает для обоих типов)
✅ **Выделение текста внутри жёлтой зоны** → корректно распознаётся как подсветка
✅ **Выделение мышкой** → работает везде (обычный текст + жёлтые зоны)
✅ **Навигация** → учитывает оба типа подсветок
✅ **Счётчик** → показывает правильное количество (исходные + пользовательские)

## Изменённые файлы

- `static/js/text-optimizer.js`:
  - `setupClickHandlers()` - добавлена обработка `.highlight-span`
  - `toggleSelectionHighlight()` - улучшена логика определения подсветок (проверка родителей)
  - `removeHighlightFromRange()` - удаление обоих типов подсветок
  - Все счётчики обновлены для работы с обоими типами

## Тестирование

1. Откройте оптимизатор текста с жёлтыми подсветками
2. **Клик по жёлтой зоне** → подсветка должна исчезнуть
3. **Выделите часть текста внутри жёлтой зоны** → при отпускании мыши подсветка должна исчезнуть
4. **Выделите обычный текст** → должна появиться новая подсветка
5. **Навигация кнопками** → должна работать для всех подсветок
6. **Счётчик** → должен показывать правильное количество
