# Реализация Real-Time Прогресса Индексации

## Дата: 18 октября 2025 г.

## Проблема
До реализации индексация выполнялась синхронно в HTTP-запросе:
- Долгое ожидание без обратной связи
- Прогресс появлялся моментально по завершении всей индексации
- Невозможно видеть обработку отдельных файлов

## Решение
Внедрена асинхронная архитектура с Server-Sent Events (SSE):

### 1. Бэкенд (`webapp/routes/search.py`)

**SSE Endpoint:**
```python
@search_bp.route('/build_index_progress')
def build_index_progress():
    """SSE endpoint для real-time прогресса индексации."""
```
- Возвращает поток событий через `Response(generate(), mimetype='text/event-stream')`
- Обновления каждые 300 мс
- Автоматическое завершение при статусе `completed` или `error`

**Фоновая индексация:**
```python
def run_indexing_in_background():
    """Функция для выполнения индексации в фоновом потоке."""
    with current_app.app_context():
        # ... индексация с progress_callback
```
- Запускается в отдельном потоке через `threading.Thread`
- Использует `app_context()` для доступа к Flask контексту
- Обновляет `IndexingProgressManager` через callback

**Endpoint запуска:**
```python
@search_bp.route('/build_index', methods=['POST'])
def build_index_route():
    # Запускает фоновый поток и немедленно возвращает ответ
    thread = threading.Thread(target=run_indexing_in_background, daemon=True)
    thread.start()
    return jsonify({'success': True, 'progress_endpoint': '/build_index_progress'})
```

### 2. Progress Manager (`webapp/services/indexing_progress.py`)

**IndexingProgress (dataclass):**
- `total_files`: общее количество файлов
- `processed_files`: обработано файлов
- `current_file`: имя текущего файла
- `status`: idle | running | completed | error
- `error`: текст ошибки (если есть)

**IndexingProgressManager (thread-safe):**
- Глобальный синглтон `_global_progress_manager`
- Потокобезопасный доступ через `threading.Lock`
- Методы: `start()`, `update()`, `complete()`, `error()`, `get_progress()`

### 3. Индексатор (`document_processor/search/two_stage_indexer.py`)

**Progress Callback:**
```python
def progress_callback(stage, processed, total, filename):
    # При первом вызове обновляем total_files
    if not total_initialized[0]:
        progress_mgr.start(total_files=total)
        total_initialized[0] = True
    
    progress_mgr.update(processed=processed, current_file=filename, ...)
```
- Вызывается после обработки каждого файла
- `stage`: 1 (текстовые) или 2 (OCR)
- `processed`: абсолютное количество обработанных файлов
- `total`: общее количество файлов (оба этапа)

### 4. Фронтенд (`static/js/script.js`)

**Функция rebuildIndexWithProgress():**
```javascript
// Запускает индексацию
fetch('/build_index', { method: 'POST' })
    .then(data => {
        // Подключается к SSE
        const eventSource = new EventSource('/build_index_progress');
        
        eventSource.onmessage = function(event) {
            const progress = JSON.parse(event.data);
            
            // Обновляет UI в реальном времени
            if (progress.status === 'running') {
                updateProgressBar(progress.processed_files, progress.total_files);
                updateCurrentFile(progress.current_file);
            }
            else if (progress.status === 'completed') {
                eventSource.close();
                showSuccess();
            }
        };
    });
```

**Обновление UI:**
- Прогресс-бар заполняется постепенно
- Отображается имя текущего обрабатываемого файла
- Счётчики `processed/total` обновляются в реальном времени
- При завершении показывается итоговое сообщение

## Архитектурная диаграмма

```
Client (Browser)                Server (Flask)                    Indexer
     |                                |                              |
     |-- POST /build_index ---------->|                              |
     |                                |-- threading.Thread --------->|
     |<-- 200 OK (immediate) ---------|                              |
     |                                |                              |
     |-- GET /build_index_progress -->|                              |
     |                                |                              |
     |<== SSE: status=running ========|<-- progress_callback --------|
     |    processed=1/10              |                              |
     |                                |                              |
     |<== SSE: status=running ========|<-- progress_callback --------|
     |    processed=2/10              |                              |
     |                                |                              |
     |         ... (каждые 300мс)     |                              |
     |                                |                              |
     |<== SSE: status=completed ======|<-- progress_mgr.complete() --|
     |    processed=10/10             |                              |
     |                                |                              |
     |-- close EventSource            |                              |
```

## Ключевые особенности

1. **Немедленный ответ:** `/build_index` возвращается мгновенно
2. **Потоковые обновления:** SSE доставляет события по мере обработки файлов
3. **Потокобезопасность:** `IndexingProgressManager` использует `threading.Lock`
4. **Graceful завершение:** SSE автоматически закрывается при `completed` или `error`
5. **Контекст Flask:** Фоновый поток использует `app_context()` для доступа к конфигурации

## Тестирование

Минимальный тест с таймаутом 10 секунд:
```python
@pytest.mark.timeout(10)
def test_progress_callback_called(tmp_path):
    """Проверяет, что progress_callback вызывается при индексации."""
    # Создаём 3 файла, запускаем индексацию, проверяем callbacks
```

Выполнение: **0.07 секунды** ✓

## Соответствие требованиям

- **FR-006 Прогресс и статусы:** ✅ Реализовано
  - Счётчики обновляются в реальном времени
  - Отображается текущий обрабатываемый файл
  - Логируются этапы индексации

## Следующие шаги

1. ✅ Real-time прогресс через SSE
2. 🔄 Оптимизация OCR (OSD, предобработка, кэширование ориентации)
3. 🔄 Инкрементальная дозапись индекса (append mode для Этапа 2)
4. 🔄 Расширенный UI с отдельными индикаторами для Этапа 1 и Этапа 2

## Технические детали

- **Python:** threading, Flask Response с генератором
- **JavaScript:** EventSource API (SSE client)
- **Формат данных:** JSON через `data: {...}\n\n`
- **Интервал обновлений:** 300 мс (настраиваемо)
- **Daemon thread:** Фоновый поток завершается при остановке сервера
