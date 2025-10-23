# restart_server.py — Быстрая перезагрузка сервера

Модуль для автоматической перезагрузки Flask-сервера с освобождением занятого порта.

## 🚀 Быстрый старт

### Самый простой способ (из корня проекта):

```bash
# Перезапуск на порту 8081 (по умолчанию для этого проекта)
python3 restart_server.py

# Перезапуск на порту 5000
python3 restart_server.py --port 5000 --command "FLASK_PORT=5000 python3 app.py"
```

### Использование в коде:

```python
from restart_server import ServerReloader

# Перезапуск сервера на порту 5000
reloader = ServerReloader(port=5000, start_command="python3 app.py")
reloader.restart()

# Только освобождение порта без запуска
reloader.free_port()
```

## 📋 Параметры командной строки

```bash
python3 restart_server.py --help
```

- `--port`, `-p` — Номер порта (по умолчанию: 8081)
- `--command`, `-c` — Команда запуска сервера (по умолчанию: "python3 app.py")
- `--wait`, `-w` — Время ожидания между остановкой и запуском в секундах (по умолчанию: 2.5)

## 💡 Примеры использования

### Быстрая перезагрузка текущего сервера:
```bash
python3 restart_server.py
```

### Перезапуск с переменными окружения:
```bash
python3 restart_server.py -p 5000 -c "FLASK_PORT=5000 python3 app.py"
```

### Только очистка порта:
```python
from restart_server import ServerReloader
ServerReloader(8081, "dummy").free_port()
```

## 🔧 Установка зависимостей (опционально)

Для более надёжной работы рекомендуется установить `psutil`:

```bash
pip install psutil
```

Без `psutil` модуль использует системные команды (`lsof` на macOS, `fuser` на Linux).

## ✅ Возможности

- ✅ Автоматическое освобождение порта
- ✅ Graceful shutdown процессов
- ✅ Работает без `psutil` (fallback на системные команды)
- ✅ Подробное логирование всех действий
- ✅ Простой API для использования в коде
- ✅ Удобный CLI интерфейс

## 📝 Методы класса ServerReloader

### `__init__(port, start_command, wait_time=2.5)`
Инициализация перезагрузчика.

### `free_port() -> bool`
Освобождает порт, завершая процессы.

### `start_server() -> Optional[subprocess.Popen]`
Запускает сервер с указанной командой.

### `restart() -> bool`
Полный цикл: освобождение → ожидание → запуск.

## 🎯 Расположение

Модуль находится в **корне проекта** для быстрого доступа:
```
web_interface/
├── restart_server.py    ← Здесь!
├── app.py
├── requirements.txt
└── ...
```

Также доступна копия в `utils/server_reloader.py` для импорта из других модулей.

---

**Совет:** Для ежедневной работы просто запускайте `python3 restart_server.py` из корня проекта! 🎉
