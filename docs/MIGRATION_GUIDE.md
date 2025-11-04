# Руководство по миграции на PostgreSQL (Increment 013)

Это пошаговое руководство по переносу данных из файлового хранилища в базу данных PostgreSQL. Подходит для перехода с каталогов `uploads/` и `index/*.json` на многопользовательскую архитектуру с хранением документов, ключей и моделей в БД.

Дата документа: 04.11.2025 (MSK)

## Что переносится

- Файлы из `uploads/` → таблица `documents` (поле `blob`, метаданные, SHA256-дедупликация)
- Ключи API из `index/api_keys.json` → таблица `api_keys` (шифрование через Fernet)
- Конфигурации моделей из `index/models.json` → таблица `ai_model_configs`

Что НЕ переносится в рамках этого шага:
- Старые логи из `logs/*.log` (начиная с Шага 14 логи пишутся в `app_logs` в БД)
- Поисковый индекс `_search_index.txt` (новый поиск работает по чанкам/векторам)

## Требования и подготовка

1) Программные компоненты
- PostgreSQL 14+ (рекомендуется 15/16)
- Расширение `pgvector` установлено в вашей БД.
	- Пример: в psql под суперпользователем: `CREATE EXTENSION IF NOT EXISTS vector;`
- Python 3.9+ и установленные зависимости из `requirements.txt`

2) Переменные окружения
- `DATABASE_URL` — строка подключения к PostgreSQL (например: `postgresql://user:pass@localhost:5432/dbname`)
- `API_ENCRYPTION_KEY` — ключ шифрования для хранения API ключей (Fernet)
	- Сгенерировать: `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`

3) Резервные копии и окно обслуживания
- Создайте бэкап каталогов `uploads/` и `index/` (скопируйте в безопасное место)
- Запланируйте короткое окно обслуживания: остановите сервер приложения на время миграции
- Убедитесь, что на диске достаточно места для чтения исходных файлов

4) Миграции и схема БД
- Примените актуальные миграции схемы (если используется Alembic) до состояния increment 013
- Убедитесь, что таблицы `users`, `documents`, `api_keys`, `ai_model_configs` доступны

## Скрипт миграции

Скрипт: `scripts/migrate_files_to_db.py`

Возможности:
- Dry-run режим (без записи в БД)
- Перенос документов с SHA256-дедупликацией
- Шифрование API ключей через Fernet
- Перенос конфигураций моделей
- Создание дефолтного пользователя `admin@localhost` (если отсутствует)

Поддерживаемые исходники:
- `uploads/` — любые файлы (медийные/текстовые), определение `content_type` через `mimetypes`
- `index/api_keys.json` — формат: `{ "openai": [ {"name":"...","key":"...","is_shared":true}, ... ], ... }`
- `index/models.json` — массив объектов моделей с полями `id`, `provider`, `name`, `input_price`, `output_price`, `context_window`, `is_active`, `is_shared`

## Пошаговая процедура

1) Остановите приложение
- Освободите занятые порты (если приложение запущено)

2) Установите переменные окружения
- Установите `DATABASE_URL` и `API_ENCRYPTION_KEY` в вашем окружении или передайте через аргументы скрипта

3) Пробный прогон (dry-run)
- Запустите скрипт без записи в БД, чтобы посмотреть, что будет мигрировано

4) Реальная миграция
- Запустите скрипт без флага `--dry-run`

5) Проверка результатов
- Сверьте количество мигрированных элементов и выполните базовые проверки

6) Переключение приложения в режим БД
- Включите использование БД (см. раздел ниже)

## Команды (macOS, zsh)

Подставьте свои значения `DATABASE_URL` и `API_ENCRYPTION_KEY`.

Пробный прогон:

```zsh
cd /Users/maksimyarikov/Desktop/Автоматизация\ закупок/Код/web_interface
DATABASE_URL="postgresql://user:pass@localhost:5432/zakupki" \
API_ENCRYPTION_KEY="<FERNET_KEY>" \
.venv/bin/python scripts/migrate_files_to_db.py --dry-run
```

Реальная миграция:

```zsh
cd /Users/maksimyarikov/Desktop/Автоматизация\ закупок/Код/web_interface
DATABASE_URL="postgresql://user:pass@localhost:5432/zakupki" \
API_ENCRYPTION_KEY="<FERNET_KEY>" \
.venv/bin/python scripts/migrate_files_to_db.py
```

Ожидаемый итог в логах:
- Создан (или найден) пользователь `admin@localhost`
- Миграция документов: `✅ <имя файла> → document_id=...`
- Миграция API ключей: `✅ <provider>: <name> → api_key_id=... (encrypted)`
- Миграция моделей: `✅ <model_id> → model_config_id=...`
- Итоговая сводка без ошибок

## Что делать, если нет `pgvector`

Если расширение `pgvector` не установлено, векторный поиск (Шаг 12–13) работать не будет. Установите расширение и примените миграции. Пример для локальной БД:

```sql
-- Выполните под суперпользователем в psql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Переключение приложения на БД (dual-mode)

Если у приложения предусмотрен флаг использования БД (например, переменная окружения `USE_DATABASE=1` или настройка `app_config.use_database`), включите его после успешной миграции. Точный способ зависит от текущей конфигурации проекта:

- Проверьте README и/или настройки приложения на предмет флага режима БД
- Перезапустите приложение и убедитесь, что эндпоинт `/health` возвращает `db_connection: ok`

## Проверка результатов (быстро)

Минимальная верификация после миграции:
- В БД появились записи в таблицах `documents`, `api_keys`, `ai_model_configs`
- Хеши (`sha256`) документов уникальны; дубликаты пропущены
- Секреты в БД хранятся в виде зашифрованного текста (`api_keys.key_ciphertext`)

Примеры команд проверки (опционально):

```zsh
# Подсчитать документы (через psql)
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM documents;"

# Проверить пользователя admin@localhost
psql "$DATABASE_URL" -c "SELECT id,email,role FROM users WHERE email='admin@localhost';"

# Быстрая Python-проверка
python - <<'PY'
import os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as c:
		docs = c.execute(text('SELECT COUNT(*) FROM documents')).scalar()
		keys = c.execute(text('SELECT COUNT(*) FROM api_keys')).scalar()
		models = c.execute(text('SELECT COUNT(*) FROM ai_model_configs')).scalar()
print({'documents': docs, 'api_keys': keys, 'models': models})
PY
```

Если приложение запущено, проверьте `/health`:

```zsh
curl -s http://localhost:8081/health | python3 -m json.tool
```

## Откат (rollback)

Скрипт поддерживает безопасный dry-run, но не выполняет автоматический откат. Если нужно откатить импорт, используйте временные метки `created_at` и/или `uploaded_at` и удалите записи, созданные в окно миграции. Пример SQL (замените дату/время на ваши):

```sql
-- Удалить документы, созданные в окно миграции
DELETE FROM documents WHERE created_at >= TIMESTAMP '2025-11-04 00:00:00+00';

-- Удалить API ключи, созданные в окно миграции
DELETE FROM api_keys WHERE created_at >= TIMESTAMP '2025-11-04 00:00:00+00';

-- Удалить конфигурации моделей, созданные в окно миграции
DELETE FROM ai_model_configs WHERE created_at >= TIMESTAMP '2025-11-04 00:00:00+00';

-- При необходимости удалить созданного дефолтного пользователя (если уверенны)
DELETE FROM users WHERE email = 'admin@localhost' AND created_at >= TIMESTAMP '2025-11-04 00:00:00+00';
```

Альтернатива: временно выключить режим БД и вернуться к файловому режиму (если он ещё поддерживается), пока причины ошибки не устранены.

## Частые проблемы и решения

- Ошибка подключения к БД — проверьте `DATABASE_URL`, права пользователя, что БД запущена
- Ошибка `pgvector` отсутствует — установите расширение (см. выше)
- Неверный `API_ENCRYPTION_KEY` — сгенерируйте валидный ключ Fernet
- Дубликаты документов — это ожидаемо, файлы с одинаковым SHA256 будут пропущены
- Большие файлы — скрипт сохраняет содержимое в `blob`; при необходимости можно расширить логику на `storage_url`
- Кодировки JSON — файлы `api_keys.json` и `models.json` читаются как UTF-8

## Безопасность

- Никогда не храните `API_ENCRYPTION_KEY` в репозитории; используйте переменные окружения/секреты
- В логах скрипта ключи и пароли не выводятся в открытом виде
- Проверьте, что доступ к БД ограничен и журналирование включено

## Вопросы

Если что-то в руководстве не совпадает с вашей конфигурацией (путь к БД, наличие Alembic, флаг dual-mode), адаптируйте соответствующие шаги под вашу среду. При необходимости создайте issue в репозитории с описанием окружения и логами запуска.

