# Статус выполнения Блока 4: Индексация из blob

**Дата:** 2025-11-10  
**Блок:** 4 из 11  
**Статус:** ✅ **ЗАВЕРШЁН** (100% выполнено)

## Выполненные изменения

### 1. Модификация импортов
**Файл:** `webapp/services/db_indexing.py`

```python
# Было:
from document_processor.extractors.text_extractor import extract_text

# Стало:
from document_processor.extractors.text_extractor import extract_text_from_bytes
```

### 2. Функция `index_document_to_db()` - чтение из blob

**Изменения:**
- ✅ Добавлен запрос `SELECT id, blob FROM documents WHERE sha256 = %s`
- ✅ Проверка наличия chunks перед возвратом (если chunks есть - skip, если нет - индексация)
- ✅ Извлечение текста из blob через `extract_text_from_bytes(document_blob, ext)`
- ✅ Fallback на чтение из файла (временная совместимость)
- ✅ Логирование процесса извлечения текста

**Логика:**
```python
# 1. Проверяем документ и blob
if document_id and has_chunks:
    return document_id  # Уже проиндексирован
    
# 2. Извлекаем текст
if document_blob:
    content = extract_text_from_bytes(document_blob, ext)  # Из blob
else:
    # Fallback (будет удалён в Блоке 9)
    content = extract_text_from_bytes(file_bytes_from_disk, ext)
    
# 3. Чанкование и сохранение
chunks = chunk_document(content, ...)
# Сохранение в БД
```

### 3. Функция переиндексации - чтение из blob

**Файл:** `webapp/services/db_indexing.py` (~строка 753)

**Изменения:**
- ✅ Запрос расширен: `SELECT ud.document_id, d.sha256, d.blob`
- ✅ Извлечение текста из blob с fallback на файл
- ✅ Обработка ошибок с graceful degradation

### 4. Создание документа при наличии ID

**Логика:**
```python
if document_id is None:
    # Создаём новый документ
    INSERT INTO documents ...
else:
    # Используем существующий ID, только обновляем связь user_documents
```

## Текущие проблемы

### ~~Проблема 1: memoryview из PostgreSQL~~ ✅ РЕШЕНА
**Симптом:** `extract_text_from_bytes` возвращал 0 символов при чтении из blob

**Причина:** PostgreSQL возвращает BYTEA как `memoryview`, а не `bytes`

**Решение:** Добавлено преобразование `bytes(document_blob) if not isinstance(document_blob, bytes)`

### ~~Проблема 2: Неправильное имя колонки~~ ✅ РЕШЕНА
**Симптом:** `psycopg2.errors.UndefinedColumn: column "length" does not exist`

**Причина:** В таблице chunks колонка называется `tokens`, а не `length`

**Решение:** Исправлен INSERT запрос на использование правильной колонки

### ~~Проблема 3: NOT NULL constraint на created_at~~ ✅ РЕШЕНА
**Симптом:** `psycopg2.errors.NotNullViolation: null value in column "created_at"`

**Причина:** Колонка created_at требует значение, но не передавалось

**Решение:** Добавлен `template="(%s, %s, %s, %s, NOW())"` в execute_values

## Следующие шаги

### ~~Немедленно (для завершения Блока 4):~~ ✅ ВЫПОЛНЕНО
1. ✅ Blob сохраняется корректно (подтверждено test_simple_blob.py)
2. ✅ Отладить почему chunks не создаются - найдены 3 проблемы (memoryview, колонка, created_at)
3. ✅ Исправить тесты `test_indexing_from_blob.py` - все 3 теста проходят
4. ✅ Запустить полный набор тестов - 27 passed, 2 skipped

### После завершения Блока 4:
- Перейти к Блоку 5 (политика prune 30%)
- Затем Блок 9 (КРИТИЧЕСКИЙ - полное отключение ФС)

## Технические детали

### Поддерживаемые форматы для извлечения из blob:
- ✅ TXT (UTF-8, CP1251, автодетект)
- ✅ JSON, CSV/TSV
- ✅ HTML/XML (с очисткой тегов)
- ✅ PDF (pdfplumber → pypdf)
- ✅ DOCX (python-docx)
- ✅ XLSX (openpyxl)
- ✅ XLS (xlrd)

### Совместимость:
- ✅ Fallback на чтение из файлов (будет удалён в Блоке 9)
- ✅ Graceful degradation при ошибках
- ✅ Логирование всех операций

## Метрики выполнения

```
Блок 1: ████████████████████ 100% ✅ Схема БД
Блок 2: ████████████████████ 100% ✅ BlobStorageService (27/29 тестов)
Блок 3: ████████████████████ 100% ✅ Экстракторы (17 тестов)
Блок 4: ████████████████████ 100% ✅ Индексация из blob (27 passed, 2 skipped)
Блок 5: ░░░░░░░░░░░░░░░░░░░░   0% ⏳ Политика prune 30%
Блоки 6-11: ░░░░░░░░░░░░░░░░░░░░   0% ⏳ Очистка и финализация
```

## Вывод

✅ **Блок 4 успешно завершён!** Функциональность чтения из blob и создания chunks полностью реализована и протестирована. Обнаружены и исправлены 3 критические проблемы:
1. Преобразование memoryview → bytes
2. Использование правильного имени колонки (tokens)
3. Добавление created_at через NOW()

**Готовность к продолжению:** 100% ✅  
**Критические блокеры:** Нет  
**Риски:** Отсутствуют  
**Следующий блок:** Блок 5 - Политика prune 30%
