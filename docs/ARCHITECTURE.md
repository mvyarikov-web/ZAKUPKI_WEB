# Архитектура приложения ZAKUPKI_WEB

## Обзор

Приложение построено по модульному принципу с использованием Flask фабрики приложений (factory pattern) и разделением на blueprints.

## Структура проекта

```
ZAKUPKI_WEB/
├── app.py                      # Точка входа для разработки (обёртка)
├── wsgi.py                     # Точка входа для продакшена (gunicorn/uwsgi)
├── webapp/                     # Основной пакет приложения
│   ├── __init__.py            # Фабрика create_app()
│   ├── config.py              # Конфигурации (Dev/Prod/Testing)
│   ├── routes/                # Blueprints с маршрутами
│   │   ├── pages.py           # Страницы (index, view)
│   │   ├── files.py           # Работа с файлами (upload, delete, download)
│   │   ├── search.py          # Поиск и индексация
│   │   └── health.py          # Health check
│   ├── services/              # Бизнес-логика
│   │   ├── files.py           # Утилиты для файлов (безопасность, валидация)
│   │   ├── indexing.py        # Обёртка над DocumentProcessor
│   │   └── state.py           # Управление состоянием (FilesState)
│   └── utils/                 # Вспомогательные утилиты
│       ├── logging.py         # Настройка логирования
│       └── errors.py          # Обработчики ошибок
├── document_processor/         # Модуль индексации/поиска (без изменений)
├── templates/                  # Jinja2 шаблоны
├── static/                     # Статические файлы (CSS, JS, images)
├── tests/                      # Тесты
├── uploads/                    # Загруженные файлы (в .gitignore)
├── index/                      # Индексные файлы (в .gitignore)
└── logs/                       # Логи приложения (в .gitignore)
```

## Ключевые компоненты

### 1. Конфигурация (webapp/config.py)

Классы конфигурации для разных окружений:
- `Config` - базовая конфигурация
- `DevConfig` - для разработки (DEBUG=True)
- `ProdConfig` - для продакшена (DEBUG=False)
- `TestingConfig` - для тестов

**Переменные окружения:**
- `FLASK_ENV` - выбор конфигурации (dev, prod, testing)
- `SECRET_KEY` - секретный ключ Flask
- `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG` - параметры dev-сервера

### 2. Фабрика приложения (webapp/__init__.py)

Функция `create_app(config_name)`:
- Создаёт Flask приложение
- Загружает конфигурацию
- Настраивает логирование
- Регистрирует blueprints
- Настраивает обработчики ошибок
- Добавляет хуки для логирования запросов

### 3. Blueprints (webapp/routes/)

#### pages.py
- `GET /` - главная страница с файлами
- `GET /view/<path>` - просмотр содержимого файла

#### files.py
- `POST /upload` - загрузка файлов
- `DELETE /delete/<path>` - удаление файла
- `DELETE /delete_folder/<path>` - удаление папки
- `GET /download/<path>` - скачивание файла
- `GET /files_json` - JSON-список файлов

#### search.py
- `POST /search` - поиск по ключевым словам
- `POST /build_index` - явная сборка индекса
- `GET /index_status` - статус индексного файла
- `GET /view_index` - просмотр сводного индекса
- `POST /clear_results` - очистка результатов

#### health.py
- `GET /health` - проверка работоспособности

### 4. Сервисы (webapp/services/)

#### files.py
Утилиты для работы с файлами:
- `is_safe_subpath()` - проверка безопасности пути
- `safe_filename()` - создание безопасных имён файлов
- `allowed_file()` - проверка расширения файла

#### indexing.py
Работа с индексацией:
- `parse_index_char_counts()` - парсинг количества символов
- `build_search_index()` - построение индекса
- `search_in_index()` - поиск по индексу
- `get_index_path()` - путь к индексному файлу

#### state.py
Управление состоянием файлов (замена глобального `file_status`):
- `FilesState` - класс с файловой блокировкой (fcntl)
- Атомарные операции чтения/записи
- Методы: `get_file_status()`, `set_file_status()`, `update_file_statuses()`

### 5. Утилиты (webapp/utils/)

#### logging.py
- `setup_logging()` - настройка логирования с ротацией
- `generate_request_id()` - генерация ID запроса

#### errors.py
- `register_error_handlers()` - регистрация обработчиков ошибок
- Обработчики: 413 (слишком большой файл), 404, 500

## Запуск

### Разработка

```bash
# Через app.py
python app.py

# Или через Flask CLI
export FLASK_APP=app.py
export FLASK_ENV=dev
flask run
```

### Продакшен

```bash
# С gunicorn
gunicorn 'wsgi:app' -w 4 -b 127.0.0.1:8081

# С uwsgi
uwsgi --http :8081 --wsgi-file wsgi.py --callable app
```

## Тестирование

```bash
# Все тесты
pytest

# Конкретные тесты
pytest tests/test_flask_endpoints.py -v

# С покрытием
pytest --cov=webapp tests/
```

## Логирование

Логи пишутся в `logs/app.log`:
- Ежедневная ротация (в полночь)
- Хранение 7 архивов
- Формат: `%(asctime)s %(levelname)s [%(name)s] %(module)s:%(lineno)d - %(message)s`
- Уровень: INFO (prod), DEBUG (dev)

Каждый HTTP-запрос логируется с:
- Request ID (rid)
- Метод и путь
- Время выполнения
- Статус код

## Безопасность

1. **Пути к файлам**: Все пути проверяются через `is_safe_subpath()` для предотвращения directory traversal
2. **Имена файлов**: Санитизация через `safe_filename()` с сохранением кириллицы
3. **Валидация**: Временные Office-файлы (~$, $) фильтруются
4. **Размер файлов**: Ограничение 100MB (MAX_CONTENT_LENGTH)
5. **Расширения**: Whitelist разрешённых форматов

## Состояние приложения

Глобальное состояние заменено на `FilesState`:
- Файл: `index/search_results.json`
- Файловая блокировка (fcntl) для атомарных операций
- Хранит статусы файлов и результаты поиска
- Thread-safe для параллельных запросов

## Миграция со старой версии

Старый монолитный `app.py` сохранён как `app_old.py`.

Новый `app.py` - тонкая обёртка, которая:
1. Импортирует `create_app` из `webapp`
2. Создаёт приложение с нужной конфигурацией
3. Запускает dev-сервер при прямом запуске

Все тесты обновлены для работы с новой структурой.

## Преимущества новой архитектуры

1. **Модульность**: Код разделён по функциональности (routes, services, utils)
2. **Тестируемость**: Factory pattern позволяет создавать изолированные тестовые приложения
3. **Конфигурируемость**: Разные конфигурации для dev/prod/testing
4. **Масштабируемость**: Легко добавлять новые blueprints и сервисы
5. **Безопасность**: Централизованные проверки и валидация
6. **Продакшен-ready**: WSGI-совместимость, proper logging, error handling
7. **Maintainability**: Чистая структура, понятные зависимости
