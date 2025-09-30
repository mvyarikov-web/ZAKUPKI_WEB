# Руководство по миграции на новую архитектуру

## Обзор изменений

Приложение было отрефакторено с монолитной структуры (один файл app.py, 1286 строк) на модульную архитектуру с использованием Flask best practices.

## Что изменилось

### 1. Структура файлов

**Было:**
```
ZAKUPKI_WEB/
├── app.py (1286 строк - весь код)
├── document_processor/
├── templates/
├── static/
└── tests/
```

**Стало:**
```
ZAKUPKI_WEB/
├── app.py (35 строк - точка входа)
├── wsgi.py (точка входа для продакшена)
├── webapp/
│   ├── __init__.py (create_app фабрика)
│   ├── config.py (конфигурации)
│   ├── routes/ (blueprints)
│   ├── services/ (бизнес-логика)
│   └── utils/ (вспомогательные функции)
├── document_processor/
├── templates/
├── static/
└── tests/
```

### 2. Импорты

**Было:**
```python
from app import app
```

**Стало:**
```python
# В коде приложения
from webapp import create_app
app = create_app('dev')

# В тестах
from webapp import create_app
app = create_app('testing')
```

### 3. Конфигурация

**Было:**
```python
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
```

**Стало:**
```python
# В webapp/config.py
class Config:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    # ...
```

Переменные окружения:
```bash
FLASK_ENV=dev  # или prod, testing
SECRET_KEY=your-secret-key
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

### 4. Глобальное состояние

**Было:**
```python
file_status = {}  # глобальная переменная
file_status['path/to/file'] = {'status': 'ok'}
```

**Стало:**
```python
from webapp.services.state import FilesState

files_state = FilesState('index/search_results.json')
files_state.set_file_status('path/to/file', 'ok', {'result': ...})
```

FilesState использует файловую блокировку (fcntl) для атомарных операций.

## Что осталось без изменений

### 1. Интерфейс пользователя
- Все маршруты работают точно так же
- HTML/CSS/JavaScript не изменились
- API эндпоинты совместимы

### 2. document_processor
- Модуль индексации/поиска не изменён
- API DocumentProcessor тот же

### 3. Шаблоны и статика
- templates/ и static/ без изменений

## Инструкции по миграции

### Для разработчиков

1. **Обновите репозиторий:**
   ```bash
   git pull origin main
   ```

2. **Установите зависимости** (если они обновлялись):
   ```bash
   pip install -r requirements.txt
   ```

3. **Запуск приложения** - без изменений:
   ```bash
   python app.py
   ```

4. **Обновите тесты** (если добавляли свои):
   ```python
   # Старый способ
   from app import app
   
   # Новый способ
   from webapp import create_app
   app = create_app('testing')
   ```

### Для DevOps

1. **Продакшен-деплой теперь через wsgi.py:**
   ```bash
   # Gunicorn
   gunicorn 'wsgi:app' -w 4 -b 127.0.0.1:8081
   
   # uWSGI
   uwsgi --http :8081 --wsgi-file wsgi.py --callable app
   ```

2. **Systemd unit пример:**
   ```ini
   [Unit]
   Description=ZAKUPKI_WEB
   After=network.target
   
   [Service]
   User=zakupki
   WorkingDirectory=/opt/zakupki_web
   Environment="FLASK_ENV=prod"
   Environment="SECRET_KEY=your-secret-key"
   ExecStart=/opt/zakupki_web/venv/bin/gunicorn 'wsgi:app' -w 4 -b 127.0.0.1:8081
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **Nginx конфигурация** - без изменений:
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8081;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }
   
   location /static {
       alias /opt/zakupki_web/static;
   }
   ```

### Если что-то сломалось

1. **Проверьте логи:**
   ```bash
   tail -f logs/app.log
   ```

2. **Запустите тесты:**
   ```bash
   pytest tests/ -v
   ```

3. **Временно откатитесь на старую версию:**
   ```bash
   cp app_old.py app.py
   # и перезапустите приложение
   ```

## Новые возможности

### 1. Конфигурация через окружение

```bash
# Быстрое переключение режимов
FLASK_ENV=dev python app.py      # Разработка
FLASK_ENV=prod gunicorn wsgi:app  # Продакшен
FLASK_ENV=testing pytest          # Тесты
```

### 2. Изолированное тестирование

```python
# Каждый тест получает свежий экземпляр приложения
@pytest.fixture
def app():
    return create_app('testing')

def test_something(app):
    with app.test_client() as client:
        # ...
```

### 3. Атомарное состояние

```python
# Безопасно для concurrent запросов
files_state = FilesState('index/search_results.json')

# Атомарное обновление нескольких статусов
files_state.update_file_statuses({
    'file1.txt': {'status': 'ok'},
    'file2.txt': {'status': 'error'}
})
```

### 4. Логирование с request ID

Каждый запрос получает уникальный ID для трейсинга:
```
2024-09-30 15:58:21,123 INFO [webapp] routes:45 - [a1b2c3d4] GET /search 0.123s 200
```

## Дополнительные ресурсы

- [Архитектура приложения](ARCHITECTURE.md)
- [Flask документация](https://flask.palletsprojects.com/)
- [Flask Blueprints](https://flask.palletsprojects.com/blueprints/)
- [Application Factory](https://flask.palletsprojects.com/patterns/appfactories/)

## Поддержка

При возникновении проблем:
1. Проверьте документацию в `docs/`
2. Посмотрите старый код в `app_old.py`
3. Создайте issue в GitHub с логами и описанием проблемы
