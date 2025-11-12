# Исправление подсветки всех найденных слов в просмотре индекса

**Дата:** 12 ноября 2025 г.  
**Задача:** В просмотре индекса должны подсвечиваться все найденные слова

## Проблема

При просмотре документа с несколькими поисковыми терминами (например, `?q=мо,договор,цд`) подсвечивались не все термины из-за ошибки в JavaScript-коде:

1. **Множественные regex с флагом `gi`**: Каждый термин проверялся отдельным регулярным выражением, и после первой проверки через `.test()` флаг сбрасывался, что приводило к пропуску последующих совпадений.

2. **Последовательные замены**: Замены выполнялись по очереди для каждого термина, что могло приводить к неполной подсветке.

3. **Дублирование логики**: Подсветка выполнялась и на бэкенде (Python), и на фронтенде (JavaScript), что могло создавать конфликты.

## Решение

### 1. Исправление JavaScript в `templates/view.html`

Изменена логика подсветки на **объединённое регулярное выражение**:

```javascript
// Было (неправильно):
const regexes = terms.map(t => new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'));
nodes.forEach(node => {
    let text = node.nodeValue;
    let replaced = false;
    regexes.forEach(re => {
        if (re.test(text)) {  // ❌ Сбрасывает lastIndex
            text = text.replace(re, ...);
            replaced = true;
        }
    });
    ...
});

// Стало (правильно):
const escapedTerms = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
const combinedRegex = new RegExp('(' + escapedTerms.join('|') + ')', 'gi');

nodes.forEach(node => {
    let text = node.nodeValue;
    if (combinedRegex.test(text)) {
        combinedRegex.lastIndex = 0;  // Сбрасываем для повторного поиска
        text = text.replace(combinedRegex, function(match) {
            return '<mark class="highlight">' + match + '</mark>';
        });
        ...
    }
});
```

**Преимущества:**
- Одно регулярное выражение для всех терминов: `/(мо|договор|цд)/gi`
- Все совпадения находятся за один проход
- Нет проблем со сбросом флага `lastIndex`

### 2. Упрощение бэкенда в `webapp/routes/pages.py`

Убрана подсветка на бэкенде — теперь вся подсветка выполняется только на фронтенде:

```python
# Было (дублирование):
if keywords:
    import re
    for keyword in keywords:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        text = pattern.sub(lambda m: f'<mark>{m.group(0)}</mark>', text)

safe_text = Markup(text.replace('<', '&lt;').replace('>', '&gt;')
                  .replace('&lt;mark&gt;', '<mark>')
                  .replace('&lt;/mark&gt;', '</mark>'))

# Стало (только экранирование):
import html
safe_text = html.escape(text)
safe_text = Markup(safe_text.replace('\n', '<br>'))
```

**Преимущества:**
- Нет дублирования логики
- Проще поддержка (один источник истины — JavaScript)
- Меньше нагрузка на бэкенд

## Тестирование

Создан тест `test_highlight_all_terms.py`, который проверяет:

1. ✅ JavaScript для подсветки присутствует в HTML
2. ✅ Используется объединённое регулярное выражение (`combinedRegex`)
3. ✅ Бэкенд не создаёт `<mark>` теги
4. ✅ Все термины из параметра `?q=` передаются корректно

**Запуск теста:**
```bash
python3 test_highlight_all_terms.py
```

## Файлы изменений

1. **`templates/view.html`** (строки 64-77):
   - Изменена логика создания регулярных выражений
   - Одно объединённое regex вместо множества

2. **`webapp/routes/pages.py`** (строки 207-218):
   - Убрана бэкенд-подсветка
   - Упрощено экранирование HTML

3. **`test_highlight_all_terms.py`** (новый):
   - Автоматический тест проверки подсветки

## Результат

✅ **Теперь подсвечиваются все найденные слова** из параметра `?q=` в просмотре индекса  
✅ Подсветка работает регистронезависимо  
✅ Нет пропущенных вхождений  
✅ Нет дублирования подсветки  

**Пример:**
```
http://127.0.0.1:8081/view/document.pdf?q=мо,договор,цд
```
Все три термина подсветятся жёлтым фоном (`<mark class="highlight">`).
