"""
Тесты для функционала промптов через БД (Блок 6 - миграция промптов).

Проверяем:
1. Сохранение промпта (POST /ai_analysis/prompts/save)
2. Загрузка промпта (GET /ai_analysis/prompts/load/<filename>)
3. Получение последнего промпта (GET /ai_analysis/prompts/last)
4. Список промптов (GET /ai_analysis/prompts/list)
5. Обновление существующего промпта
"""
from __future__ import annotations

import json
from flask import Response


def test_save_prompt_success(auth_client) -> None:
    """Сохранение нового промпта через POST /ai_analysis/prompts/save."""
    payload = {
        'prompt': 'Проанализируй текст и выдели ключевые моменты',
        'filename': 'test_prompt_1'
    }
    
    response: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload),
        content_type='application/json'
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'сохранён' in data['message'] or 'обновлён' in data['message']
    assert 'prompt' in data
    assert data['prompt']['name'] == 'test_prompt_1'
    assert data['prompt']['content'] == payload['prompt']


def test_save_prompt_empty_text(auth_client) -> None:
    """Попытка сохранить пустой промпт должна вернуть 400."""
    payload = {
        'prompt': '   ',  # только пробелы
        'filename': 'empty_prompt'
    }
    
    response: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload),
        content_type='application/json'
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'пуст' in data['message'].lower()


def test_save_prompt_no_filename(auth_client) -> None:
    """Попытка сохранить промпт без имени файла должна вернуть 400."""
    payload = {
        'prompt': 'Какой-то текст',
        'filename': ''
    }
    
    response: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload),
        content_type='application/json'
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert 'имя файла' in data['message'].lower()


def test_update_existing_prompt(auth_client) -> None:
    """Обновление существующего промпта (сохранение с тем же filename)."""
    filename = 'updatable_prompt'
    
    # Сохраняем первый вариант
    payload1 = {
        'prompt': 'Первая версия промпта',
        'filename': filename
    }
    response1: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload1),
        content_type='application/json'
    )
    assert response1.status_code == 200
    
    # Обновляем промпт
    payload2 = {
        'prompt': 'Вторая версия промпта (обновлённая)',
        'filename': filename
    }
    response2: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload2),
        content_type='application/json'
    )
    assert response2.status_code == 200
    data2 = response2.get_json()
    assert data2['success'] is True
    assert 'обновлён' in data2['message'].lower()
    
    # Проверяем, что промпт обновился
    response3: Response = auth_client.get(f'/ai_analysis/prompts/load/{filename}')
    assert response3.status_code == 200
    data3 = response3.get_json()
    assert data3['prompt'] == payload2['prompt']


def test_load_prompt_success(auth_client) -> None:
    """Загрузка существующего промпта через GET /ai_analysis/prompts/load/<filename>."""
    # Сначала сохраняем промпт
    save_payload = {
        'prompt': 'Тестовый промпт для загрузки',
        'filename': 'loadable_prompt'
    }
    auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(save_payload),
        content_type='application/json'
    )
    
    # Загружаем промпт
    response: Response = auth_client.get('/ai_analysis/prompts/load/loadable_prompt')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['prompt'] == save_payload['prompt']
    assert data['filename'] == 'loadable_prompt'
    assert 'created_at' in data


def test_load_nonexistent_prompt(auth_client) -> None:
    """Попытка загрузить несуществующий промпт должна вернуть 404."""
    response: Response = auth_client.get('/ai_analysis/prompts/load/nonexistent_prompt_xyz')
    
    assert response.status_code == 404
    data = response.get_json()
    assert data['success'] is False
    assert 'не найден' in data['message'].lower()


def test_get_last_prompt_when_empty(auth_client) -> None:
    """Получение последнего промпта когда их нет."""
    # Примечание: тест может не сработать если в БД уже есть промпты от других тестов
    # Этот тест проверяет только структуру ответа
    response: Response = auth_client.get('/ai_analysis/prompts/last')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    # Может быть либо промпт, либо None
    if data['prompt'] is None:
        assert 'нет' in data['message'].lower()


def test_get_last_prompt_after_save(auth_client) -> None:
    """Получение последнего промпта после сохранения."""
    # Сохраняем промпт
    save_payload = {
        'prompt': 'Последний промпт для теста',
        'filename': 'last_test_prompt'
    }
    auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(save_payload),
        content_type='application/json'
    )
    
    # Получаем последний
    response: Response = auth_client.get('/ai_analysis/prompts/last')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['prompt'] is not None
    assert 'filename' in data
    assert 'created_at' in data


def test_list_prompts(auth_client) -> None:
    """Получение списка всех промптов пользователя."""
    # Сохраняем несколько промптов
    prompts_to_save = [
        {'prompt': 'Промпт 1', 'filename': 'list_test_1'},
        {'prompt': 'Промпт 2', 'filename': 'list_test_2'},
        {'prompt': 'Промпт 3', 'filename': 'list_test_3'}
    ]
    
    for p in prompts_to_save:
        auth_client.post(
            '/ai_analysis/prompts/save',
            data=json.dumps(p),
            content_type='application/json'
        )
    
    # Получаем список
    response: Response = auth_client.get('/ai_analysis/prompts/list')
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'prompts' in data
    assert isinstance(data['prompts'], list)
    
    # Проверяем, что наши промпты есть в списке
    filenames = [p['filename'] for p in data['prompts']]
    assert 'list_test_1' in filenames
    assert 'list_test_2' in filenames
    assert 'list_test_3' in filenames


def test_prompt_workflow_full_cycle(auth_client) -> None:
    """Полный цикл: сохранение → список → загрузка → обновление → загрузка."""
    filename = 'workflow_test'
    
    # 1. Сохранение
    save_payload = {
        'prompt': 'Исходная версия промпта',
        'filename': filename
    }
    response1: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(save_payload),
        content_type='application/json'
    )
    assert response1.status_code == 200
    
    # 2. Проверка в списке
    response2: Response = auth_client.get('/ai_analysis/prompts/list')
    assert response2.status_code == 200
    data2 = response2.get_json()
    filenames = [p['filename'] for p in data2['prompts']]
    assert filename in filenames
    
    # 3. Загрузка
    response3: Response = auth_client.get(f'/ai_analysis/prompts/load/{filename}')
    assert response3.status_code == 200
    data3 = response3.get_json()
    assert data3['prompt'] == save_payload['prompt']
    
    # 4. Обновление
    update_payload = {
        'prompt': 'Обновлённая версия промпта',
        'filename': filename
    }
    response4: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(update_payload),
        content_type='application/json'
    )
    assert response4.status_code == 200
    data4 = response4.get_json()
    assert 'обновлён' in data4['message'].lower()
    
    # 5. Загрузка обновлённого
    response5: Response = auth_client.get(f'/ai_analysis/prompts/load/{filename}')
    assert response5.status_code == 200
    data5 = response5.get_json()
    assert data5['prompt'] == update_payload['prompt']


def test_prompts_with_cyrillic(auth_client) -> None:
    """Проверка работы с кириллицей в промптах и именах файлов."""
    payload = {
        'prompt': 'Проанализируй документ и выдели ключевые моменты по закупкам',
        'filename': 'промпт_кириллица'
    }
    
    # Сохранение
    response1: Response = auth_client.post(
        '/ai_analysis/prompts/save',
        data=json.dumps(payload, ensure_ascii=False),
        content_type='application/json; charset=utf-8'
    )
    assert response1.status_code == 200
    
    # Загрузка
    response2: Response = auth_client.get(f'/ai_analysis/prompts/load/{payload["filename"]}')
    assert response2.status_code == 200
    data2 = response2.get_json()
    assert data2['prompt'] == payload['prompt']
    assert data2['filename'] == payload['filename']
