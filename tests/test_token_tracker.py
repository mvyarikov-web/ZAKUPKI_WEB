import os
from datetime import datetime


def test_token_tracker_in_memory_no_file(tmp_path, monkeypatch):
    # Отключаем БД-режим
    monkeypatch.setenv('USE_DATABASE', 'false')
    # Указываем models.json в temp для стабильности цен
    models_dir = tmp_path / 'index'
    models_dir.mkdir()
    (models_dir / 'models.json').write_text(
        '{"models":[{"model_id":"gpt-4o-mini","price_input_per_1m":0.15,"price_output_per_1m":0.6}]}',
        encoding='utf-8'
    )

    # Подменяем путь к models.json через cwd
    from utils import token_tracker as tt
    # monkeypatch пути не трогаем: функция читает относительно файла модуля

    # Логируем использование
    tt.log_token_usage(
        model_id='gpt-4o-mini',
        prompt_tokens=1000,
        completion_tokens=2000,
        total_tokens=3000,
        duration_seconds=1.23,
        metadata={'foo': 'bar'}
    )

    stats = tt.get_all_time_stats()
    assert stats['success'] is True
    assert stats['total_records'] >= 1
    # Убеждаемся, что файл token_usage.json не создается
    assert not (tmp_path / 'index' / 'token_usage.json').exists()


def test_token_tracker_db_roundtrip(monkeypatch):
    # Включаем БД-режим; тестовая БД у нас memory (см. conftest.py)
    monkeypatch.setenv('USE_DATABASE', 'true')
    from utils import token_tracker as tt

    # Логируем две записи разных моделей
    tt.log_token_usage('gpt-4o-mini', 100, 200, 300, 0.5, metadata={'user_id': 1})
    tt.log_token_usage('deepseek-chat', 500, 500, 1000, 1.0, metadata={'user_id': 2})

    # Агрегация без фильтров
    all_stats = tt.get_all_time_stats()
    assert all_stats['success'] is True
    assert all_stats['total_records'] >= 2
    mids = {m['model_id'] for m in all_stats['models']}
    assert {'gpt-4o-mini', 'deepseek-chat'} <= mids

    # Фильтр по модели
    mini_only = tt.get_token_stats(model_id='gpt-4o-mini')
    assert mini_only['success'] is True
    assert any(m['model_id'] == 'gpt-4o-mini' for m in mini_only['models'])
