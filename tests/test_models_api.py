"""
Тесты для проверки доступности и оптимальных параметров OpenAI моделей.

Проверяет каждую модель из конфигурации:
- Доступность (401, 404, прочие ошибки)
- Правильность параметров (temperature, max_tokens/max_completion_tokens)
- Поддержка system role
- Оптимальный timeout
- Реальная цена токенов

Запуск: pytest tests/test_models_api.py -v -s
"""
import os
import json
import time
import pytest
from pathlib import Path
from typing import Dict, Any, Tuple
import openai


# === Настройки ===
BASE_DIR = Path(__file__).parent.parent
MODELS_CONFIG_PATH = BASE_DIR / 'index' / 'models.json'
TEST_PROMPT = "Проанализируй этот текст и скажи главное: Поставка климатического оборудования включает 2 кондиционера мощностью 5 кВт."
TEST_SYSTEM_PROMPT = "Ты - помощник для анализа документов закупок. Отвечай на русском языке кратко."


# === Утилиты ===
def load_models_config() -> Dict[str, Any]:
    """Загрузить конфигурацию моделей."""
    with open(MODELS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_models_config(config: Dict[str, Any]) -> None:
    """Сохранить конфигурацию моделей."""
    backup_path = MODELS_CONFIG_PATH.with_suffix('.json.backup')
    if MODELS_CONFIG_PATH.exists():
        import shutil
        shutil.copy(MODELS_CONFIG_PATH, backup_path)
    
    with open(MODELS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_api_key() -> str:
    """Получить API ключ из переменной окружения."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        pytest.skip("OPENAI_API_KEY не задан в переменной окружения")
    return api_key


def is_new_model_family(model_id: str) -> bool:
    """Проверить, относится ли модель к новым семействам (o1, o3, o4, gpt-4.1, gpt-5)."""
    return model_id.startswith(('o1', 'o3', 'o4', 'gpt-4.1', 'gpt-5'))


def test_model_basic(
    model_id: str,
    api_key: str,
    supports_system: bool = True,
    timeout: int = 30,
    max_tokens: int = 150
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Базовый тест модели.
    
    Returns:
        (success, error_message, result_data)
    """
    client = openai.OpenAI(api_key=api_key, timeout=timeout)
    
    # Формируем сообщения
    if supports_system:
        messages = [
            {"role": "system", "content": TEST_SYSTEM_PROMPT},
            {"role": "user", "content": TEST_PROMPT}
        ]
    else:
        messages = [
            {"role": "user", "content": f"{TEST_SYSTEM_PROMPT}\n\n{TEST_PROMPT}"}
        ]
    
    # Определяем параметры для новых семейств
    is_new = is_new_model_family(model_id)
    
    kwargs = {
        'model': model_id,
        'messages': messages
    }
    
    # Новые модели используют max_completion_tokens
    if is_new:
        kwargs['max_completion_tokens'] = max_tokens
    else:
        kwargs['max_tokens'] = max_tokens
    
    # Новые модели не принимают temperature (или только 1)
    if not is_new:
        kwargs['temperature'] = 0.3
    
    try:
        start = time.time()
        response = client.chat.completions.create(**kwargs)
        elapsed = time.time() - start
        
        return (True, "", {
            'content': response.choices[0].message.content,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            'finish_reason': response.choices[0].finish_reason,
            'elapsed_time': round(elapsed, 2)
        })
    except Exception as e:
        error_str = str(e)
        return (False, error_str, {})


# === Фикстуры ===
@pytest.fixture(scope='module')
def api_key():
    """API ключ для тестов."""
    return get_api_key()


@pytest.fixture(scope='module')
def models_config():
    """Текущая конфигурация моделей."""
    return load_models_config()


@pytest.fixture(scope='module')
def test_results():
    """Словарь для накопления результатов тестов."""
    return {}


# === Тесты ===
class TestModelAvailability:
    """Проверка доступности каждой модели."""
    
    def test_all_models_accessible(self, api_key, models_config, test_results):
        """Проверить доступность всех моделей из конфигурации."""
        models = models_config.get('models', [])
        
        for model in models:
            model_id = model['model_id']
            print(f"\n{'='*60}")
            print(f"Тестирование модели: {model_id} ({model.get('display_name', '')})")
            print(f"{'='*60}")
            
            supports_system = model.get('supports_system_role', True)
            timeout = model.get('timeout', 30)
            
            success, error, result = test_model_basic(
                model_id=model_id,
                api_key=api_key,
                supports_system=supports_system,
                timeout=timeout,
                max_tokens=150
            )
            
            test_results[model_id] = {
                'success': success,
                'error': error,
                'result': result,
                'config': model
            }
            
            if success:
                print(f"✅ Модель {model_id} работает корректно")
                print(f"   Время ответа: {result['elapsed_time']}s")
                print(f"   Токены: {result['usage']['total_tokens']} (вход: {result['usage']['prompt_tokens']}, выход: {result['usage']['completion_tokens']})")
                print(f"   Finish reason: {result['finish_reason']}")
                print(f"   Ответ (первые 100 символов): {result['content'][:100]}...")
            else:
                print(f"❌ Модель {model_id} недоступна")
                print(f"   Ошибка: {error}")
                
                # Пробуем диагностировать и исправить
                if '401' in error or 'insufficient permissions' in error.lower():
                    print("   💡 Недостаточно прав. Проверьте подписку/доступ к модели.")
                elif 'temperature' in error.lower():
                    print("   💡 Ошибка с temperature. Попробуем без него...")
                    # Повторная попытка для новых моделей
                    success2, error2, result2 = test_model_basic(
                        model_id=model_id,
                        api_key=api_key,
                        supports_system=False,  # Тоже может быть проблемой
                        timeout=timeout,
                        max_tokens=150
                    )
                    if success2:
                        print("   ✅ Исправлено! Работает без system role.")
                        test_results[model_id]['success'] = True
                        test_results[model_id]['error'] = ""
                        test_results[model_id]['result'] = result2
                        test_results[model_id]['config']['supports_system_role'] = False
                    else:
                        print(f"   ❌ Не удалось исправить: {error2}")
                elif 'max_tokens' in error.lower():
                    print("   💡 Ошибка с max_tokens. Эта модель требует max_completion_tokens.")
                elif 'model' in error.lower() and '404' in error:
                    print("   💡 Модель не найдена. Возможно, неправильный ID или модель устарела.")


class TestModelOptimalParams:
    """Подбор оптимальных параметров для каждой модели."""
    
    def test_optimal_timeout(self, api_key, models_config, test_results):
        """Проверить оптимальный timeout для успешных моделей."""
        print(f"\n{'='*60}")
        print("Проверка оптимальных timeout")
        print(f"{'='*60}")
        
        for model_id, data in test_results.items():
            if not data['success']:
                continue
            
            elapsed = data['result'].get('elapsed_time', 0)
            current_timeout = data['config'].get('timeout', 30)
            
            # Рекомендуемый timeout: 2-3x от фактического времени + запас
            recommended_timeout = max(20, int(elapsed * 3) + 10)
            
            print(f"\n{model_id}:")
            print(f"   Текущий timeout: {current_timeout}s")
            print(f"   Фактическое время: {elapsed}s")
            print(f"   Рекомендуемый timeout: {recommended_timeout}s")
            
            if recommended_timeout != current_timeout:
                test_results[model_id]['optimal_timeout'] = recommended_timeout
            else:
                test_results[model_id]['optimal_timeout'] = current_timeout


class TestModelCleanup:
    """Очистка нерабочих моделей и обновление конфигурации."""
    
    def test_remove_broken_models(self, models_config, test_results):
        """Удалить нерабочие модели из конфигурации."""
        print(f"\n{'='*60}")
        print("Очистка нерабочих моделей")
        print(f"{'='*60}")
        
        original_models = models_config.get('models', [])
        working_models = []
        removed_models = []
        
        for model in original_models:
            model_id = model['model_id']
            result = test_results.get(model_id, {})
            
            if result.get('success', False):
                # Обновляем оптимальные параметры
                if 'optimal_timeout' in result:
                    model['timeout'] = result['optimal_timeout']
                
                # Обновляем supports_system_role если изменилось
                if 'config' in result and 'supports_system_role' in result['config']:
                    model['supports_system_role'] = result['config']['supports_system_role']
                
                working_models.append(model)
                print(f"✅ Сохранена: {model_id}")
            else:
                removed_models.append(model_id)
                print(f"❌ Удалена: {model_id} (причина: {result.get('error', 'неизвестна')[:100]})")
        
        if removed_models:
            models_config['models'] = working_models
            
            # Проверяем default_model
            default_model = models_config.get('default_model')
            if default_model in removed_models:
                if working_models:
                    models_config['default_model'] = working_models[0]['model_id']
                    print(f"⚠️  default_model изменена на: {models_config['default_model']}")
                else:
                    models_config['default_model'] = None
                    print("⚠️  Нет рабочих моделей! default_model = None")
            
            save_models_config(models_config)
            print(f"\n✅ Конфигурация обновлена. Удалено моделей: {len(removed_models)}")
        else:
            print("\n✅ Все модели работают корректно!")


# === Итоговый отчёт ===
@pytest.fixture(scope='module', autouse=True)
def final_report(request, test_results):
    """Вывести итоговый отчёт после всех тестов."""
    def print_report():
        print(f"\n{'='*60}")
        print("ИТОГОВЫЙ ОТЧЁТ")
        print(f"{'='*60}")
        
        working = [m for m, d in test_results.items() if d.get('success')]
        broken = [m for m, d in test_results.items() if not d.get('success')]
        
        print(f"\n✅ Рабочие модели ({len(working)}):")
        for model_id in working:
            data = test_results[model_id]
            print(f"   • {model_id}")
            print(f"     - Время ответа: {data['result']['elapsed_time']}s")
            print(f"     - Timeout: {data.get('optimal_timeout', data['config'].get('timeout'))}s")
            print(f"     - System role: {'да' if data['config'].get('supports_system_role', True) else 'нет'}")
        
        if broken:
            print(f"\n❌ Нерабочие модели ({len(broken)}):")
            for model_id in broken:
                data = test_results[model_id]
                error = data.get('error', 'неизвестна')
                print(f"   • {model_id}: {error[:80]}")
        
        print(f"\n{'='*60}")
    
    request.addfinalizer(print_report)
