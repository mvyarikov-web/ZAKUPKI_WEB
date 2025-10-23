# Модуль server_reloader.py

Автоматическая перезагрузка Flask-сервера с освобождением занятого порта.

## Установка зависимостей

Рекомендуется установить `psutil` для корректной работы:

```bash
pip install psutil
```

Если `psutil` недоступен, модуль использует системные команды (`lsof` на macOS, `fuser` на Linux).

## Использование

### Как библиотека

```python
from utils.server_reloader import ServerReloader

# Создаём перезагрузчик для порта 5000
reloader = ServerReloader(
    port=5000,
    start_command="python3 app.py",
    wait_time=2.5  # секунды ожидания между остановкой и запуском
)

# Перезапускаем сервер
success = reloader.restart()
```

### Как скрипт из командной строки

```bash
# Базовый запуск (порт 5000, команда "python3 app.py")
python utils/server_reloader.py

# С кастомными параметрами
python utils/server_reloader.py --port 8081 --command "python3 app.py" --wait 3

# Справка
python utils/server_reloader.py --help
```

## Методы класса ServerReloader

### `__init__(port, start_command, wait_time=2.5)`
Инициализация перезагрузчика.

**Параметры:**
- `port` (int): Номер порта для освобождения
- `start_command` (str): Команда запуска сервера
- `wait_time` (float): Время ожидания между остановкой и запуском (секунды)

### `free_port() -> bool`
Освобождает порт, завершая процессы, которые его занимают.

**Возвращает:** `True` если порт освобождён успешно, `False` при ошибке.

### `start_server() -> Optional[subprocess.Popen]`
Запускает сервер с указанной командой.

**Возвращает:** Объект `subprocess.Popen` запущенного процесса или `None` при ошибке.

### `restart() -> bool`
Полный цикл перезапуска: освобождение порта → ожидание → запуск сервера.

**Возвращает:** `True` если перезапуск прошёл успешно, `False` при ошибке.

## Примеры

### Перезапуск Flask на порту 8081

```python
from utils.server_reloader import ServerReloader

reloader = ServerReloader(
    port=8081,
    start_command="FLASK_PORT=8081 python3 app.py"
)
reloader.restart()
```

### Только освобождение порта

```python
from utils.server_reloader import ServerReloader

reloader = ServerReloader(port=5000, start_command="dummy")
reloader.free_port()  # Только освобождаем порт без запуска
```

### Из командной строки с переменными окружения

```bash
python utils/server_reloader.py \
    --port 5000 \
    --command "FLASK_PORT=5000 python3 app.py" \
    --wait 3
```

## Особенности

- **Graceful shutdown**: Сначала `terminate()`, затем `kill()` если процесс не завершился
- **Кроссплатформенность**: psutil (все ОС) или fallback на `lsof` (macOS) / `fuser` (Linux)
- **Логирование**: Все действия пишутся в stdout с таймстампами
- **Независимость**: Не зависит от основной логики проекта, можно использовать отдельно

## Требования

- Python 3.7+
- psutil (опционально, но рекомендуется): `pip install psutil`
- macOS/Linux для fallback-режима без psutil
