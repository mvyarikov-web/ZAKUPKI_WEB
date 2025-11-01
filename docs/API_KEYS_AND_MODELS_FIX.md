# Исправление работы моделей DeepSeek и OpenAI

**Дата:** 1 ноября 2025  
**Проблема:** DeepSeek анализ сразу завершался с ошибкой без детального сообщения

## Выявленные проблемы

1. **Отсутствие поля `provider` в конфигурации моделей**
   - В `index/models.json` не было явного указания провайдера для каждой модели
   - Код определял провайдер по префиксу `model_id`, но тесты требовали явное поле

2. **Недостаточное логирование ошибок API**
   - При ошибках подключения к API не выводились детальные сообщения
   - Сложно было диагностировать проблему

3. **Некорректный тест для DeepSeek Reasoner**
   - Тест ожидал текст в поле `content`
   - DeepSeek Reasoner может возвращать результат в `reasoning_content`

## Внесенные изменения

### 1. Обновлена конфигурация моделей (`index/models.json`)

Добавлены поля для всех моделей:

**OpenAI модели:**
```json
{
  "model_id": "gpt-4o",
  "provider": "openai",
  ...
}
```

**DeepSeek модели:**
```json
{
  "model_id": "deepseek-chat",
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com",
  ...
}
```

### 2. Улучшено логирование (`webapp/routes/ai_rag.py`)

Добавлено детальное логирование ошибок API:
```python
except Exception as api_err:
    error_str = str(api_err)
    current_app.logger.error(f'Ошибка API {model_id}: {error_str}', exc_info=True)
```

В функцию `_get_api_client()` добавлена информация о статусе ключа:
```python
current_app.logger.info(f'Используется DeepSeek API для модели {model_id}, ключ: {"присутствует" if deepseek_key and len(deepseek_key) > 10 else "ОТСУТСТВУЕТ!"}')
```

### 3. Исправлен тест DeepSeek Reasoner (`tests/test_deepseek_api.py`)

Теперь проверяются оба поля:
```python
message_content = message.content or ""
reasoning_content = getattr(message, 'reasoning_content', None) or ""

# Хотя бы одно из полей должно быть заполнено
assert (message_content or reasoning_content), "Оба поля пустые"
```

### 4. Добавлены поля `provider` для UX

Обновлены изменения в `static/js/rag-analysis.js`:
- **Зеленое сообщение** (≤5% битых символов): `✅ 2.1% битых символов, оптимизация не требуется`
- **Желтое предупреждение** (>5%): `⚠️ 15.3% битых символов, рекомендуется оптимизация!`

## Результаты тестирования

### DeepSeek API
```bash
$ pytest tests/test_deepseek_api.py -v
✅ test_deepseek_api_key_exists PASSED
✅ test_deepseek_chat_connection PASSED
✅ test_deepseek_reasoner_connection PASSED
✅ test_deepseek_api_with_timeout PASSED
✅ test_deepseek_models_in_config PASSED

5 passed in 10.87s
```

### OpenAI API
```bash
$ pytest tests/test_openai_api.py -v
✅ test_openai_api_key_exists PASSED
✅ test_openai_connection PASSED
✅ test_openai_models_in_config PASSED

3 passed in 2.27s
```

### Проверка подключений

**DeepSeek:**
```
🔑 DeepSeek ключ найден: sk-ea785...
✅ Подключение успешно!
📝 Ответ: Привет! (Privet!)
📊 Токены: input=13, output=7
```

**OpenAI:**
```
🔑 OpenAI ключ найден: sk-proj-...
✅ Подключение успешно!
📝 Ответ: Привет! (Privet!)
📊 Токены: input=20, output=8
```

## Итоговая конфигурация

### Активные модели (6 шт.)
| Модель | Провайдер | Статус | Цена (input/output per 1M) |
|--------|-----------|--------|---------------------------|
| gpt-4o | openai | ✅ | $2.5 / $10.0 |
| gpt-4o-mini | openai | ✅ | $0.15 / $0.6 |
| o1 | openai | ✅ | $15.0 / $60.0 |
| gpt-3.5-turbo | openai | ✅ | $0.5 / $1.5 |
| deepseek-chat | openai | ✅ | $0.028 / $0.42 |
| deepseek-reasoner | deepseek | ✅ | $0.028 / $0.42 |

**Модель по умолчанию:** `deepseek-chat`

### API ключи
- ✅ **DeepSeek:** `sk-e...3171` (активен)
- ✅ **OpenAI:** `sk-p...jEYA` (активен)

## Как использовать

1. **Откройте приложение:** `http://localhost:8081`
2. **Выберите модель** в окне "AI анализ"
3. **Запустите анализ** - теперь обе модели работают корректно

## Диагностика проблем

Если анализ не работает, проверьте:

1. **API ключи настроены:**
   ```bash
   python3 -c "from utils.api_keys_manager import get_api_keys_manager; print(get_api_keys_manager().list_keys())"
   ```

2. **Логи приложения:**
   ```bash
   tail -f logs/app.log | grep -i "deepseek\|error\|api"
   ```

3. **Статус сервера:**
   ```bash
   curl http://localhost:8081/health
   ```

## Следующие шаги

- [ ] Добавить валидацию API ключей при сохранении
- [ ] Реализовать автоматическое обновление статуса ключей
- [ ] Добавить мониторинг расхода токенов по провайдерам
- [ ] Создать UI для переключения между провайдерами

---

**Статус:** ✅ Полностью работоспособно  
**Тестировано:** DeepSeek Chat, DeepSeek Reasoner, GPT-4o-mini, GPT-3.5-turbo
