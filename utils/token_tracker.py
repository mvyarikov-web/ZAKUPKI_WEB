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


def ensure_stats_file():
    """Создаёт файл статистики, если его нет"""
    if not TOKEN_STATS_FILE.exists():
        TOKEN_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'records': []}, f, ensure_ascii=False, indent=2)


def log_token_usage(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    metadata: Optional[Dict] = None
):
    """
    Записывает использование токенов в лог
    
    Args:
        model_id: ID модели (например, 'gpt-4o-mini')
        prompt_tokens: Количество токенов в промпте
        completion_tokens: Количество токенов в ответе
        total_tokens: Общее количество токенов
        metadata: Дополнительная информация (файлы, промпт и т.д.)
    """
    try:
        ensure_stats_file()
        
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
            'metadata': metadata or {}
        }
        
        data['records'].append(record)
        
        # Сохраняем обновлённую статистику
        with open(TOKEN_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Записано использование токенов: {model_id} - {total_tokens} токенов")
        
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
                    'first_used': record['timestamp'],
                    'last_used': record['timestamp']
                }
            
            stats = models_stats[mid]
            stats['total_requests'] += 1
            stats['total_tokens'] += record.get('total_tokens', 0)
            stats['prompt_tokens'] += record.get('prompt_tokens', 0)
            stats['completion_tokens'] += record.get('completion_tokens', 0)
            
            # Обновляем временные метки
            if record['timestamp'] < stats['first_used']:
                stats['first_used'] = record['timestamp']
            if record['timestamp'] > stats['last_used']:
                stats['last_used'] = record['timestamp']
        
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
