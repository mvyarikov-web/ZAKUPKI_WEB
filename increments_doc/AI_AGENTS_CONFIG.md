# Конфигурация AI‑моделей и провайдеров (актуальная)

Краткая сводка реальных настроек ИИ‑моделей, провайдеров и переменных окружения, используемых в текущем коде (RAG/AI‑анализ).

## Источники правды
- Конфиг моделей: `index/models.json` (может быть переопределён через `RAG_MODELS_FILE`).
- Маршруты/клиент провайдера: `webapp/routes/ai_rag.py` (функции `_get_api_client`, `_load_models_config*`).
- RAG‑сервис: `webapp/services/rag_service.py` (векторный поиск, генерация, параметры анализа).
- Ключи API: менеджер ключей (`webapp/utils/api_keys_adapter.py`, эндпоинты `/api_keys/*`) + переменные окружения.
- Учёт токенов/стоимости: `utils/token_tracker.py` + модель `TokenUsage` (БД).

## Переменные окружения
- OPENAI_API_KEY — ключ OpenAI (дефолтный, также используется как фолбэк для других провайдеров при отсутствии их ключей).
- DEEPSEEK_API_KEY — ключ DeepSeek.
- PPLX_API_KEY или PERPLEXITY_API_KEY — ключ Perplexity.
- DATABASE_URL — строка подключения к PostgreSQL (RAG/хранилище).
- OPTIONAL: OPENAI_TIMEOUT — таймаут HTTP‑запросов к LLM (по умолчанию 90 сек).
- OPTIONAL: API_ENCRYPTION_KEY — ключ Fernet для шифрования API‑ключей в БД.

Примечание: при наличии БД ключи предпочтительно брать через API ключей (`/api_keys/...`), затем из переменных окружения.

## Определение провайдера модели
Определяется по префиксу `model_id` (код не опирается на поле `provider` в JSON):
- `sonar*` → Perplexity: base_url `https://api.perplexity.ai`, ключ из менеджера `perplexity` → `PPLX_API_KEY`/`PERPLEXITY_API_KEY` (фолбэк: `OPENAI_API_KEY`).
- `deepseek*` → DeepSeek: base_url `https://api.deepseek.com`, ключ из менеджера `deepseek` → `DEEPSEEK_API_KEY` (фолбэк: `OPENAI_API_KEY`).
- Иначе → OpenAI: базовый клиент OpenAI, ключ из менеджера `openai` → `OPENAI_API_KEY`.

## Конфигурация моделей (models.json)
Файл `index/models.json` хранит список моделей и экономику. Ключевые поля модели:
- model_id: строковый ID модели (например, `gpt-4o-mini`, `deepseek-chat`, `sonar-pro`).
- display_name, description: имя и описание в UI.
- context_window_tokens: окно контекста, если известно.
- price_input_per_1m, price_output_per_1m: цены за 1M входных/выходных токенов (USD).
- pricing_model: `per_token` (по умолчанию) или `per_request` (для Perplexity‑поиска можно указать `price_per_1000_requests`).
- timeout: таймаут запроса (секунды).
- supports_system_role: поддержка системного промпта (true/false).
- provider (опционально): для отображения; фактический провайдер определяется по `model_id` (см. выше).

В корне:
- default_model: модель по умолчанию для UI/эндпоинтов.

Мини‑пример:
```
{
  "models": [
    {
      "model_id": "gpt-4o-mini",
      "display_name": "GPT-4o Mini",
      "context_window_tokens": 128000,
      "price_input_per_1m": 0.15,
      "price_output_per_1m": 0.6,
      "enabled": true,
      "timeout": 120,
      "supports_system_role": true
    },
    {
      "model_id": "deepseek-chat",
      "display_name": "DeepSeek Chat",
      "price_input_per_1m": 0.028,
      "price_output_per_1m": 0.42,
      "enabled": true
    },
    {
      "model_id": "sonar-pro",
      "display_name": "Perplexity Sonar Pro",
      "pricing_model": "per_request",
      "price_per_1000_requests": 5,
      "supports_search": true
    }
  ],
  "default_model": "deepseek-chat"
}
```

## Режим веб‑поиска (Perplexity)
- При моделях `sonar*` и включённом поиске (`search_params` задан или форс‑флаг) в запрос добавляются параметры поиска через `extra_body`.
- В режиме поиска для Sonar удаляется `response_format` (JSON) для стабильности.
- В режиме «без поиска» для Sonar выставляется `extra_body: {"disable_search": true}`; `max_tokens` намеренно не передаём.
- Нормализация и применение параметров: `webapp/services/search/manager.py` (поля вроде `max_results`, `search_domain_filter`, `search_recency_filter`, `country`, и т. д.).

## Учёт токенов и стоимости
- Стоимость на основе токенов: расчёт по полям `price_input_per_1m` и `price_output_per_1m` из конфигурации.
- Стоимость per‑request (Perplexity): `price_per_1000_requests` → стоимость за запрос = `price_per_1000 / 1000`.
- Фактическое потребление логируется в `TokenUsage` (БД): `user_id`, `model_id`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `duration_seconds`, `cost_usd`, `metadata`, `created_at`.
- Агрегации (за месяц/всё время) доступны через функции `utils/token_tracker.py` (DB‑first, с in‑memory фолбэком).

## RAG: параметры по умолчанию
- RAG_ENABLED: включение/выключение (конфиг приложения).
- RAG_CHUNK_SIZE: размер чанка (по умолчанию 2000 токенов).
- RAG_CHUNK_OVERLAP: перекрытие в предложениях (по умолчанию 3).
- RAG_TOP_K: число чанков в контексте (по умолчанию 5).
- RAG_MIN_SIMILARITY: порог схожести (по умолчанию 0.7).
- RAG_EMBEDDING_MODEL: модель эмбеддингов (по умолчанию `text-embedding-3-small`).
- RAG_DEFAULT_MODEL: дефолтная модель генерации для RAG (если не указана явная модель).

## Практические заметки
- Если `index/models.json` отсутствует или повреждён, код поднимет дефолтную конфигурацию с `gpt-4o-mini`.
- Таймаут берётся из модели (`timeout`) либо из `OPENAI_TIMEOUT` (по умолчанию 90 сек).
- Для стабильной работы Sonar в поисковом режиме не задавайте `max_tokens` и `response_format`.
- Менеджер ключей позволяет хранить провайдерские ключи в БД (шифрование через `API_ENCRYPTION_KEY`).

---
Этот файл отражает фактическую конфигурацию на момент правки. При изменениях моделей/провайдеров обновляйте: `index/models.json`, `_get_api_client` и данный документ.
