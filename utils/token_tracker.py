"""
Модуль для отслеживания использования токенов AI-моделей.

Изменения (инкремент 015 CLEAN):
- Убрана запись в локальный файл index/token_usage.json
- Добавлена запись в БД (таблица TokenUsage) при доступности БД
- При недоступности БД — in-memory буфер (процессный), чтобы не терять данные
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

# Курс доллара к рублю (можно обновлять периодически)
USD_TO_RUB = 95.0  # Примерный курс

# Признак использования БД (для ранней инициализации вне Flask контекста)
USE_DATABASE = os.environ.get('USE_DATABASE', 'false').lower() in ('true', '1', 'yes', 'on')

_MEM_BUFFER: List[Dict] = []  # процессный буфер на случай отсутствия БД


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
        # Рассчитываем стоимость
        cost_info = _calculate_cost(model_id, prompt_tokens, completion_tokens)

        record = {
            'timestamp': datetime.now().isoformat(),
            'model_id': model_id,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'duration_seconds': float(duration_seconds) if duration_seconds is not None else None,
            'cost_usd': cost_info['cost_usd'],
            'cost_rub': cost_info['cost_rub'],
            'input_cost_usd': cost_info['input_cost_usd'],
            'output_cost_usd': cost_info['output_cost_usd'],
            'metadata': metadata or {}
        }

        # Пытаемся записать в БД
        if USE_DATABASE:
            try:
                from webapp.db import get_db, TokenUsage  # type: ignore
                # Берём первую сессию из генератора
                db = next(get_db())
                try:
                    # Создаём таблицу при первом использовании (если миграции не запускались)
                    try:
                        bind = db.get_bind()
                        TokenUsage.__table__.create(bind=bind, checkfirst=True)
                    except Exception:
                        pass
                    # user_id может быть в metadata
                    user_id = None
                    if metadata and isinstance(metadata, dict):
                        user_id = metadata.get('user_id')
                    # Конвертируем денежные значения в целые (центы/копейки)
                    cents = lambda x: int(round(float(x) * 100))
                    kopecks = lambda x: int(round(float(x) * 100))
                    obj = TokenUsage(
                        user_id=user_id,
                        model_id=model_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        duration_seconds=int(duration_seconds) if duration_seconds is not None else None,
                        cost_usd=cents(cost_info['cost_usd']),
                        cost_rub=kopecks(cost_info['cost_rub']),
                        input_cost_usd=cents(cost_info['input_cost_usd']),
                        output_cost_usd=cents(cost_info['output_cost_usd']),
                        metadata_json=metadata or {},
                    )
                    db.add(obj)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
            except Exception as db_err:
                logger.debug(f"DB недоступна для записи TokenUsage, используем память: {db_err}")
                _MEM_BUFFER.append(record)
        else:
            # В файловый режим не пишем — только память
            _MEM_BUFFER.append(record)

        # Информативный лог
        try:
            rub_str = f"{record['cost_rub']:.2f} ₽"
        except Exception:
            rub_str = "? ₽"
        dur_str = f", {duration_seconds:.2f}s" if duration_seconds else ""
        logger.info(
            f"Токены: {model_id} - {total_tokens} токенов, {rub_str}{dur_str}"
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
        records: List[Dict]
        if USE_DATABASE:
            try:
                from webapp.db import get_db, TokenUsage  # type: ignore
                db = next(get_db())
                try:
                    # Создаём таблицу при первом использовании (если миграции не запускались)
                    try:
                        bind = db.get_bind()
                        TokenUsage.__table__.create(bind=bind, checkfirst=True)
                    except Exception:
                        pass
                    q = db.query(TokenUsage)
                    # Фильтры по датам
                    if start_date:
                        from datetime import datetime as _dt
                        start_dt = _dt.fromisoformat(start_date)
                        q = q.filter(TokenUsage.created_at >= start_dt)
                    if end_date:
                        from datetime import datetime as _dt
                        end_dt = _dt.fromisoformat(end_date + 'T23:59:59')
                        q = q.filter(TokenUsage.created_at <= end_dt)
                    if model_id:
                        q = q.filter(TokenUsage.model_id == model_id)
                    rows = q.all()
                    records = []
                    for r in rows:
                        # Обратно преобразуем денежные значения из целых
                        rec = {
                            'timestamp': r.created_at.isoformat(),
                            'model_id': r.model_id,
                            'prompt_tokens': r.prompt_tokens,
                            'completion_tokens': r.completion_tokens,
                            'total_tokens': r.total_tokens,
                            'duration_seconds': r.duration_seconds,
                            'cost_usd': (r.cost_usd or 0) / 100.0,
                            'cost_rub': (r.cost_rub or 0) / 100.0,
                            'input_cost_usd': (r.input_cost_usd or 0) / 100.0,
                            'output_cost_usd': (r.output_cost_usd or 0) / 100.0,
                            'metadata': r.metadata_json or {},
                        }
                        records.append(rec)
                finally:
                    db.close()
            except Exception as db_err:
                logger.debug(f"DB недоступна для чтения TokenUsage, используем память: {db_err}")
                records = list(_MEM_BUFFER)
        else:
            records = list(_MEM_BUFFER)
        
        # Фильтрация по датам для in-memory/пост-обработки
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
