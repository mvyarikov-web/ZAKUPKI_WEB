"""
Модуль для отслеживания использования токенов AI-моделей
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Путь к файлу со статистикой токенов
TOKEN_STATS_FILE = Path(__file__).parent.parent / 'index' / 'token_usage.json'

# Курс доллара к рублю (можно обновлять периодически)
USD_TO_RUB = 95.0  # Примерный курс


def ensure_stats_file():
    """Создаёт файл статистики, если его нет"""
    if not TOKEN_STATS_FILE.exists():
        TOKEN_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'records': []}, f, ensure_ascii=False, indent=2)


def _load_models_config() -> Dict:
    """Загружает конфигурацию моделей с ценами"""
    try:
        models_file = Path(__file__).parent.parent / 'index' / 'models.json'
        with open(models_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {m['model_id']: m for m in config.get('models', [])}
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации моделей: {e}")
        return {}


def _calculate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> Dict:
    """
    Рассчитывает стоимость запроса в USD и RUB
    
    Returns:
        Dict с ключами: cost_usd, cost_rub, input_cost_usd, output_cost_usd
    """
    models_config = _load_models_config()
    
    if model_id not in models_config:
        return {
            'cost_usd': 0.0,
            'cost_rub': 0.0,
            'input_cost_usd': 0.0,
            'output_cost_usd': 0.0
        }
    
    model = models_config[model_id]
    price_input = model.get('price_input_per_1m', 0)
    price_output = model.get('price_output_per_1m', 0)
    
    # Стоимость в USD
    input_cost_usd = (prompt_tokens / 1_000_000) * price_input
    output_cost_usd = (completion_tokens / 1_000_000) * price_output
    total_cost_usd = input_cost_usd + output_cost_usd
    
    # Стоимость в RUB
    total_cost_rub = total_cost_usd * USD_TO_RUB
    
    return {
        'cost_usd': round(total_cost_usd, 6),
        'cost_rub': round(total_cost_rub, 4),
        'input_cost_usd': round(input_cost_usd, 6),
        'output_cost_usd': round(output_cost_usd, 6)
    }


def log_token_usage(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_seconds: Optional[float] = None,
    metadata: Optional[Dict] = None
):
    """
    Записывает использование токенов в лог
    
    Args:
        model_id: ID модели (например, 'gpt-4o-mini')
        prompt_tokens: Количество токенов в промпте
        completion_tokens: Количество токенов в ответе
        total_tokens: Общее количество токенов
        duration_seconds: Время выполнения запроса в секундах
        metadata: Дополнительная информация (файлы, промпт и т.д.)
    """
    try:
        ensure_stats_file()
        
        # Рассчитываем стоимость
        cost_info = _calculate_cost(model_id, prompt_tokens, completion_tokens)
        
        # Читаем текущую статистику
        with open(TOKEN_STATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Добавляем новую запись
        record = {
            'timestamp': datetime.now().isoformat(),
            'model_id': model_id,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'duration_seconds': duration_seconds,
            'cost_usd': cost_info['cost_usd'],
            'cost_rub': cost_info['cost_rub'],
            'input_cost_usd': cost_info['input_cost_usd'],
            'output_cost_usd': cost_info['output_cost_usd'],
            'metadata': metadata or {}
        }
        
        data['records'].append(record)
        
        # Сохраняем обновлённую статистику
        with open(TOKEN_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(
            f"Записано использование токенов: {model_id} - {total_tokens} токенов, "
            f"{cost_info['cost_rub']:.2f} ₽, {duration_seconds:.2f}s" if duration_seconds else ""
        )
        
    except Exception as e:
        logger.error(f"Ошибка записи статистики токенов: {e}")


def get_token_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model_id: Optional[str] = None
) -> Dict:
    """
    Получает статистику использования токенов с фильтрацией
    
    Args:
        start_date: Начальная дата в формате ISO (YYYY-MM-DD)
        end_date: Конечная дата в формате ISO (YYYY-MM-DD)
        model_id: Фильтр по ID модели
    
    Returns:
        Dict с агрегированной статистикой по моделям
    """
    try:
        ensure_stats_file()
        
        with open(TOKEN_STATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        records = data.get('records', [])
        
        # Фильтрация по датам
        if start_date:
            start_dt = datetime.fromisoformat(start_date)
            records = [r for r in records if datetime.fromisoformat(r['timestamp']) >= start_dt]
        
        if end_date:
            end_dt = datetime.fromisoformat(end_date + 'T23:59:59')
            records = [r for r in records if datetime.fromisoformat(r['timestamp']) <= end_dt]
        
        # Фильтрация по модели
        if model_id:
            records = [r for r in records if r['model_id'] == model_id]
        
        # Агрегируем по моделям
        models_stats = {}
        for record in records:
            mid = record['model_id']
            if mid not in models_stats:
                models_stats[mid] = {
                    'model_id': mid,
                    'total_requests': 0,
                    'total_tokens': 0,
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_cost_usd': 0.0,
                    'total_cost_rub': 0.0,
                    'total_duration_seconds': 0.0,
                    'durations': [],  # Для расчёта средней скорости
                    'first_used': record['timestamp'],
                    'last_used': record['timestamp']
                }
            
            stats = models_stats[mid]
            stats['total_requests'] += 1
            stats['total_tokens'] += record.get('total_tokens', 0)
            stats['prompt_tokens'] += record.get('prompt_tokens', 0)
            stats['completion_tokens'] += record.get('completion_tokens', 0)
            stats['total_cost_usd'] += record.get('cost_usd', 0)
            stats['total_cost_rub'] += record.get('cost_rub', 0)
            
            # Время выполнения
            duration = record.get('duration_seconds')
            if duration is not None:
                stats['total_duration_seconds'] += duration
                stats['durations'].append(duration)
            
            # Обновляем временные метки
            if record['timestamp'] < stats['first_used']:
                stats['first_used'] = record['timestamp']
            if record['timestamp'] > stats['last_used']:
                stats['last_used'] = record['timestamp']
        
        # Рассчитываем средние значения
        for mid, stats in models_stats.items():
            if stats['total_requests'] > 0:
                stats['avg_cost_usd'] = round(stats['total_cost_usd'] / stats['total_requests'], 6)
                stats['avg_cost_rub'] = round(stats['total_cost_rub'] / stats['total_requests'], 4)
                
                if stats['durations']:
                    stats['avg_duration_seconds'] = round(
                        sum(stats['durations']) / len(stats['durations']), 2
                    )
                else:
                    stats['avg_duration_seconds'] = 0.0
            else:
                stats['avg_cost_usd'] = 0.0
                stats['avg_cost_rub'] = 0.0
                stats['avg_duration_seconds'] = 0.0
            
            # Округляем итоговые значения
            stats['total_cost_usd'] = round(stats['total_cost_usd'], 6)
            stats['total_cost_rub'] = round(stats['total_cost_rub'], 2)
            stats['total_duration_seconds'] = round(stats['total_duration_seconds'], 2)
            
            # Удаляем временный массив длительностей
            del stats['durations']
        
        return {
            'success': True,
            'models': list(models_stats.values()),
            'total_records': len(records),
            'period': {
                'start': start_date,
                'end': end_date
            }
        }
        
    except Exception as e:
        logger.error(f"Ошибка чтения статистики токенов: {e}")
        return {
            'success': False,
            'error': str(e),
            'models': []
        }


def get_current_month_stats() -> Dict:
    """Получает статистику за текущий месяц"""
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return get_token_stats(start_date=start_of_month.strftime('%Y-%m-%d'))


def get_all_time_stats() -> Dict:
    """Получает статистику за всё время"""
    return get_token_stats()
