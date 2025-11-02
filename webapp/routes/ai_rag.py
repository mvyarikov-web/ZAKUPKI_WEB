"""Blueprint для RAG-анализа документов."""
import os
import json
import re
import io
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file, render_template
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.shared import OxmlElement
from docx.oxml.ns import qn

from webapp.services.rag_service import get_rag_service
from webapp.services.chunking import TextChunker
from utils.token_tracker import log_token_usage, get_token_stats, get_current_month_stats, get_all_time_stats
from utils.api_keys_manager_multiple import get_api_keys_manager_multiple


ai_rag_bp = Blueprint('ai_rag', __name__, url_prefix='/ai_rag')


def _load_models_config() -> Dict[str, Any]:
    """Загрузить и при необходимости мигрировать конфигурацию моделей из файла.

    Поддерживаются варианты:
    - отсутствует файл: возвращаем дефолтную конфигурацию;
    - файл-список (устаревший формат): оборачиваем в объект с ключом models;
    - ключи цен с заглавной M (price_input_per_1M): нормализуем в price_*_per_1m.
    """
    models_file = current_app.config.get('RAG_MODELS_FILE')

    # Базовая дефолтная конфигурация
    default_cfg: Dict[str, Any] = {
        'models': [
            {
                'model_id': 'gpt-4o-mini',
                'display_name': 'GPT-4o Mini',
                'context_window_tokens': 128000,
                'price_input_per_1m': 0.0,
                'price_output_per_1m': 0.0,
                'enabled': True,
            }
        ],
        'default_model': 'gpt-4o-mini',
    }

    if not models_file or not os.path.exists(models_file):
        return default_cfg

    try:
        with open(models_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        current_app.logger.error(f'Ошибка загрузки models.json: {e}')
        return default_cfg

    migrated = False

    # Если старый формат (список моделей), оборачиваем в объект
    if isinstance(raw, list):
        config: Dict[str, Any] = {'models': raw, 'default_model': (raw[0].get('model_id') if raw and isinstance(raw[0], dict) else 'gpt-4o-mini')}
        migrated = True
    elif isinstance(raw, dict):
        config = raw
    else:
        # Некорректный формат
        current_app.logger.warning('models.json имеет некорректный формат, используется дефолтная конфигурация')
        return default_cfg

    # Нормализация структуры models
    models = config.get('models', [])
    if not isinstance(models, list):
        models = []
        config['models'] = models
        migrated = True

    normalized_models: List[Dict[str, Any]] = []
    for m in models:
        if not isinstance(m, dict):
            migrated = True
            continue
        model_id = m.get('model_id') or m.get('id') or 'unknown-model'
        display_name = m.get('display_name') or model_id
        context_window = m.get('context_window_tokens') or m.get('context_window') or 0
        # Нормализация цен (поддержка старых ключей с заглавной M)
        price_in = m.get('price_input_per_1m')
        if price_in is None and 'price_input_per_1M' in m:
            price_in = m.get('price_input_per_1M')
            migrated = True
        price_out = m.get('price_output_per_1m')
        if price_out is None and 'price_output_per_1M' in m:
            price_out = m.get('price_output_per_1M')
            migrated = True
        enabled = m.get('enabled')
        if enabled is None:
            enabled = True
            migrated = True
        
        # Миграция timeout - если нет, устанавливаем 30 сек
        timeout = m.get('timeout')
        if timeout is None:
            timeout = 30
            migrated = True
        
        # Сохраняем описание, если оно есть
        description = m.get('description', '')
        
        # Сохраняем supports_system_role (для o-моделей)
        supports_system_role = m.get('supports_system_role', True)
        
        # Сохраняем provider и base_url для DeepSeek моделей
        provider = m.get('provider', 'openai')  # По умолчанию openai
        base_url = m.get('base_url')  # Опционально для DeepSeek

        model_dict = {
            'model_id': model_id,
            'display_name': display_name,
            'description': description,
            'context_window_tokens': int(context_window) if isinstance(context_window, (int, float)) else 0,
            'price_input_per_1m': float(price_in) if price_in is not None else 0.0,
            'price_output_per_1m': float(price_out) if price_out is not None else 0.0,
            'enabled': bool(enabled),
            'timeout': int(timeout) if isinstance(timeout, (int, float)) else 30,
            'supports_system_role': bool(supports_system_role),
            'provider': provider,
        }
        
        # Добавляем base_url только если он указан
        if base_url:
            model_dict['base_url'] = base_url
        
        # Добавляем поддержку режима поиска для Perplexity моделей
        if m.get('supports_search'):
            model_dict['supports_search'] = True
            model_dict['price_per_1000_requests'] = float(m.get('price_per_1000_requests', 5.0))
            model_dict['search_params'] = m.get('search_params', {})
            # Сохраняем флаг search_enabled если он есть
            if 'search_enabled' in m:
                model_dict['search_enabled'] = bool(m.get('search_enabled', False))
        
        normalized_models.append(model_dict)

    if normalized_models != models:
        config['models'] = normalized_models
        migrated = True

    # Дефолтная модель
    default_model = config.get('default_model')
    if not default_model:
        config['default_model'] = normalized_models[0]['model_id'] if normalized_models else 'gpt-4o-mini'
        migrated = True

    # Если произошла миграция — сохраняем обратно
    if migrated:
        try:
            _save_models_config(config)
            current_app.logger.info('models.json был автоматически мигрирован в актуальный формат')
        except Exception as e:
            current_app.logger.warning(f'Не удалось сохранить мигрированный models.json: {e}')

    return config


def _save_models_config(config: Dict[str, Any]):
    """Сохранить конфигурацию моделей в файл (атомарно)."""
    models_file = current_app.config.get('RAG_MODELS_FILE')
    if not models_file:
        return

    tmp_path = models_file + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, models_file)
    except Exception:
        # В случае ошибки при записи временный файл может остаться — пробуем удалить
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def _calculate_cost(model_config: Dict[str, Any], usage: Dict[str, int], request_count: int = 1) -> Dict[str, float]:
    """
    Универсальный расчет стоимости для разных моделей тарификации.
    
    Args:
        model_config: Конфигурация модели из models.json
        usage: Словарь с токенами {'input_tokens': N, 'output_tokens': M}
        request_count: Количество запросов (для моделей с тарификацией per_request)
        
    Returns:
        Dict со стоимостью: {
            'input': float,
            'output': float, 
            'total': float,
            'currency': str,
            'pricing_model': str
        }
    """
    pricing_model = model_config.get('pricing_model', 'per_token')
    
    if pricing_model == 'per_request':
        # Тарификация по запросам (Search API)
        price_per_1k = model_config.get('price_per_1000_requests', 0.0)
        total_cost = (request_count / 1000) * price_per_1k
        
        return {
            'input': 0.0,
            'output': 0.0,
            'total': round(total_cost, 6),
            'currency': 'USD',
            'pricing_model': 'per_request',
            'requests_count': request_count
        }
    else:
        # Стандартная тарификация по токенам
        price_input = model_config.get('price_input_per_1m', 0.0)
        price_output = model_config.get('price_output_per_1m', 0.0)
        
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)
        
        cost_input = (input_tokens / 1_000_000) * price_input
        cost_output = (output_tokens / 1_000_000) * price_output
        total_cost = cost_input + cost_output
        
        return {
            'input': round(cost_input, 6),
            'output': round(cost_output, 6),
            'total': round(total_cost, 6),
            'currency': 'USD',
            'pricing_model': 'per_token'
        }


def _fetch_openai_models() -> List[Dict[str, Any]]:
    """Попробовать получить список моделей из OpenAI SDK. Возвращает [] при ошибке.

    Возвращаем упрощённые записи: {model_id, display_name, context_window_tokens}
    Цены не извлекаем (нет публичного API) — оставляем 0, пользователь задаёт вручную.
    """
    try:
        from openai import OpenAI  # type: ignore
        api_key = current_app.config.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return []
        timeout = current_app.config.get('OPENAI_TIMEOUT', 90)
        client = OpenAI(api_key=api_key, timeout=timeout)
        models = client.models.list()
        items = []
        # Оставляем только chat/completions/omni семейство (эвристика по id)
        for m in getattr(models, 'data', []) or []:
            mid = getattr(m, 'id', None) or (isinstance(m, dict) and m.get('id'))
            if not mid:
                continue
            # Фильтрация по известным префиксам
            if any(mid.startswith(p) for p in ('gpt-', 'o', 'chatgpt', 'gpt-4o')):
                items.append({
                    'model_id': mid,
                    'display_name': mid,
                    'context_window_tokens': 0,  # нет надёжного поля в API
                    'price_input_per_1m': 0.0,
                    'price_output_per_1m': 0.0,
                    'enabled': True,
                })
        return items
    except Exception as e:
        # Не логируем как ошибку сервера маршрута — просто вернём пусто
        current_app.logger.info(f'Не удалось получить список моделей OpenAI: {e}')
        return []


@ai_rag_bp.route('/models/refresh', methods=['POST'])
def refresh_models():
    """Обновить список моделей: объединить локальные и OpenAI (если доступно).

    Поведение:
    - Пытаемся получить список из OpenAI; если нет — считаем, что добавлений 0.
    - Сливаем по model_id: новые добавляем с нулевыми ценами; существующим не трогаем цены и enabled.
    - Сохраняем конфигурацию. Возвращаем числа added/updated.
    """
    try:
        config = _load_models_config()
        local_models = {m['model_id']: m for m in config.get('models', [])}
        remote_models = _fetch_openai_models()

        added = 0
        updated = 0

        for rm in remote_models:
            mid = rm['model_id']
            if mid in local_models:
                # Обновим только display/context, цены не трогаем
                lm = local_models[mid]
                new_display = rm.get('display_name') or mid
                new_ctx = int(rm.get('context_window_tokens') or 0)
                if lm.get('display_name') != new_display:
                    lm['display_name'] = new_display
                    updated += 1
                if lm.get('context_window_tokens') != new_ctx:
                    lm['context_window_tokens'] = new_ctx
                    updated += 1
            else:
                # Добавляем новую модель с нулевыми ценами
                local_models[mid] = {
                    'model_id': mid,
                    'display_name': rm.get('display_name') or mid,
                    'context_window_tokens': int(rm.get('context_window_tokens') or 0),
                    'price_input_per_1m': 0.0,
                    'price_output_per_1m': 0.0,
                    'enabled': True,
                    'timeout': 30,
                }
                added += 1

        # Пересобираем список, сохраняем порядок алфавитный по display_name
        merged_list = list(local_models.values())
        merged_list.sort(key=lambda x: (str(x.get('display_name') or x.get('model_id'))).lower())
        config['models'] = merged_list

        # Если default_model отсутствует — проставим первый
        if not config.get('default_model') and merged_list:
            config['default_model'] = merged_list[0]['model_id']

        _save_models_config(config)

        return jsonify({'success': True, 'added': added, 'updated': updated, 'count': len(merged_list)}), 200
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models/refresh: {e}')
        # Возвращаем 200 с success=false, чтобы фронтенд не падал на non-JSON/500
        return jsonify({'success': False, 'message': f'Не удалось обновить модели: {str(e)}'}), 200


@ai_rag_bp.route('/models/available', methods=['GET'])
def get_available_models():
    """
    Получить список всех доступных моделей из OpenAI API.
    
    Returns:
        JSON со списком моделей
    """
    try:
        available = _fetch_openai_models()
        
        if not available:
            return jsonify({
                'success': False,
                'message': 'Не удалось получить список моделей из OpenAI API. Проверьте API ключ.'
            }), 200
        
        return jsonify({
            'success': True,
            'models': available
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models/available: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка при получении списка моделей: {str(e)}'
        }), 200


@ai_rag_bp.route('/models/add', methods=['POST'])
def add_selected_models():
    """
    Добавить выбранные модели в конфигурацию.
    
    Ожидает JSON:
        {
            "model_ids": ["gpt-4", "gpt-3.5-turbo", ...]
        }
    
    Returns:
        JSON с результатом операции
    """
    try:
        data = request.get_json()
        if not data or 'model_ids' not in data:
            return jsonify({
                'success': False,
                'message': 'Требуется поле model_ids'
            }), 400
        
        model_ids = data['model_ids']
        if not isinstance(model_ids, list) or not model_ids:
            return jsonify({
                'success': False,
                'message': 'model_ids должен быть непустым списком'
            }), 400
        
        # Получить все доступные модели
        available = _fetch_openai_models()
        available_dict = {m['model_id']: m for m in available}
        
        # Загрузить текущую конфигурацию
        config = _load_models_config()
        current_models = config.get('models', [])
        current_ids = {m['model_id'] for m in current_models}
        
        added = 0
        for mid in model_ids:
            if mid in current_ids:
                continue  # Уже есть
            
            if mid in available_dict:
                # Добавляем модель из доступных
                new_model = available_dict[mid].copy()
                new_model['timeout'] = 30  # Дефолтный timeout
                current_models.append(new_model)
                added += 1
        
        if added > 0:
            config['models'] = current_models
            _save_models_config(config)
            current_app.logger.info(f'Добавлено моделей: {added}')
        
        return jsonify({
            'success': True,
            'added': added,
            'total': len(current_models)
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models/add: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка при добавлении моделей: {str(e)}'
        }), 500


@ai_rag_bp.route('/models/default', methods=['PUT'])
def set_default_model():
    """
    Установить модель по умолчанию.
    
    Ожидает JSON:
    {
        "model_id": "gpt-4o-mini"
    }
    
    Returns:
        JSON с результатом
    """
    try:
        data = request.get_json()
        
        if not data or 'model_id' not in data:
            return jsonify({
                'success': False,
                'message': 'Не передан model_id'
            }), 400
        
        model_id = data['model_id']
        config = _load_models_config()
        
        # Проверяем, что модель существует
        model_exists = any(m['model_id'] == model_id for m in config.get('models', []))
        
        if not model_exists:
            return jsonify({
                'success': False,
                'message': f'Модель {model_id} не найдена'
            }), 404
        
        # Устанавливаем модель по умолчанию
        config['default_model'] = model_id
        _save_models_config(config)
        
        current_app.logger.info(f'Модель по умолчанию изменена на: {model_id}')
        
        return jsonify({
            'success': True,
            'message': 'Модель по умолчанию сохранена',
            'default_model': model_id
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models/default: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка сохранения: {str(e)}'
        }), 500


@ai_rag_bp.route('/models', methods=['GET'])
def get_models():
    """
    Получить список доступных моделей.
    
    Returns:
        JSON со списком моделей
    """
    try:
        config = _load_models_config()
        
        return jsonify({
            'success': True,
            'models': config.get('models', []),
            'default_model': config.get('default_model', 'gpt-4o-mini')
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка получения моделей: {str(e)}'
        }), 500


@ai_rag_bp.route('/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    """
    Удалить модель из конфигурации.
    
    Args:
        model_id: ID модели для удаления
        
    Returns:
        JSON с результатом операции
    """
    try:
        config = _load_models_config()
        models = config.get('models', [])
        
        # Проверка: должна остаться хотя бы одна модель
        if len(models) <= 1:
            return jsonify({
                'success': False,
                'error': 'Нельзя удалить последнюю модель. Должна оставаться хотя бы одна модель.'
            }), 400
        
        # Найти модель для удаления
        model_to_delete = None
        for model in models:
            if model.get('model_id') == model_id:
                model_to_delete = model
                break
        
        if not model_to_delete:
            return jsonify({
                'success': False,
                'error': f'Модель "{model_id}" не найдена'
            }), 404
        
        # Удалить модель из списка
        models = [m for m in models if m.get('model_id') != model_id]
        config['models'] = models
        
        # Если удаляемая модель была default, назначить новый default
        if config.get('default_model') == model_id:
            config['default_model'] = models[0].get('model_id') if models else 'gpt-4o-mini'
            current_app.logger.info(f'Default модель изменена на {config["default_model"]} после удаления {model_id}')
        
        # Сохранить обновленную конфигурацию
        _save_models_config(config)
        
        current_app.logger.info(f'Модель {model_id} успешно удалена')
        
        return jsonify({
            'success': True,
            'message': f'Модель "{model_to_delete.get("display_name", model_id)}" успешно удалена',
            'new_default_model': config.get('default_model')
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка при удалении модели {model_id}: {e}')
        return jsonify({
            'success': False,
            'error': f'Ошибка при удалении модели: {str(e)}'
        }), 500


@ai_rag_bp.route('/models', methods=['POST'])
def update_model_prices():
    """
    Обновить цены и параметры для модели.
    
    Ожидает JSON:
    {
        "model_id": "gpt-4o-mini",
        "price_input_per_1m": 0.15,
        "price_output_per_1m": 0.60,
        "timeout": 30
    }
    
    Returns:
        JSON с результатом обновления
    """
    try:
        data = request.get_json()
        
        if not data or 'model_id' not in data:
            return jsonify({
                'success': False,
                'message': 'Не указан model_id'
            }), 400
        
        model_id = data['model_id']
        price_input = data.get('price_input_per_1m')
        price_output = data.get('price_output_per_1m')
        price_per_1000_requests = data.get('price_per_1000_requests')
        pricing_model = data.get('pricing_model')
        timeout = data.get('timeout')
        
        # Загружаем конфигурацию
        config = _load_models_config()
        
        # Находим модель и обновляем параметры
        found = False
        for model in config.get('models', []):
            if model['model_id'] == model_id:
                if price_input is not None:
                    model['price_input_per_1m'] = float(price_input)
                if price_output is not None:
                    model['price_output_per_1m'] = float(price_output)
                if price_per_1000_requests is not None:
                    model['price_per_1000_requests'] = float(price_per_1000_requests)
                if pricing_model is not None:
                    model['pricing_model'] = pricing_model
                if timeout is not None:
                    model['timeout'] = int(timeout)
                found = True
                break
        
        if not found:
            return jsonify({
                'success': False,
                'message': f'Модель {model_id} не найдена'
            }), 404
        
        # Сохраняем обновлённую конфигурацию
        _save_models_config(config)
        
        return jsonify({
            'success': True,
            'message': 'Настройки модели обновлены'
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models POST: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка обновления цен: {str(e)}'
        }), 500


@ai_rag_bp.route('/models/search_params', methods=['POST'])
def update_search_params():
    """
    Обновить параметры поиска для модели Search API.
    
    Ожидает JSON:
    {
        "model_id": "perplexity-search-api",
        "search_params": {
            "max_results": 10,
            "search_domain_filter": "",
            ...
        }
    }
    
    Returns:
        JSON с результатом обновления
    """
    try:
        data = request.get_json()
        
        if not data or 'model_id' not in data or 'search_params' not in data:
            return jsonify({
                'success': False,
                'message': 'Не указаны model_id или search_params'
            }), 400
        
        model_id = data['model_id']
        search_params = data['search_params']
        
        # Загружаем конфигурацию
        config = _load_models_config()
        
        # Находим модель и обновляем параметры
        found = False
        for model in config.get('models', []):
            if model['model_id'] == model_id:
                model['search_params'] = search_params
                found = True
                break
        
        if not found:
            return jsonify({
                'success': False,
                'message': f'Модель {model_id} не найдена'
            }), 404
        
        # Сохраняем обновлённую конфигурацию
        _save_models_config(config)
        
        return jsonify({
            'success': True,
            'message': 'Параметры поиска обновлены'
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/models/search_params POST: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка обновления параметров: {str(e)}'
        }), 500


@ai_rag_bp.route('/estimate', methods=['POST'])
def estimate_request():
    """
    Оценить запрос (токены и стоимость) без выполнения.
    
    Ожидает JSON:
    {
        "file_paths": ["path1", "path2"],
        "prompt": "текст промпта",
        "model_id": "gpt-4o-mini",
        "top_k": 5,
        "expected_output_tokens": 600
    }
    
    Returns:
        JSON с оценкой токенов и стоимости
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Не переданы данные'
            }), 400
        
        file_paths = data.get('file_paths', [])
        prompt = data.get('prompt', '')
        model_id = data.get('model_id', 'gpt-4o-mini')
        top_k = data.get('top_k', 5)
        expected_output_tokens = data.get('expected_output_tokens', 600)
        
        if not file_paths:
            return jsonify({
                'success': False,
                'message': 'Не выбраны файлы'
            }), 400
        
        if not prompt:
            return jsonify({
                'success': False,
                'message': 'Не указан промпт'
            }), 400
        
        # Получаем конфигурацию модели
        config = _load_models_config()
        model_config = None
        
        for m in config.get('models', []):
            if m['model_id'] == model_id:
                model_config = m
                break
        
        if not model_config:
            return jsonify({
                'success': False,
                'message': f'Модель {model_id} не найдена'
            }), 404
        
        # Получаем RAG-сервис
        rag_service = get_rag_service()
        
        if not rag_service.db_available:
            return jsonify({
                'success': False,
                'message': 'База данных недоступна. RAG не настроен.'
            }), 503
        
        # Получаем чанки для оценки (без векторного поиска, просто по количеству)
        # Примерная оценка: системный промпт + промпт пользователя + чанки
        
        chunker = TextChunker()
        
        # Системный промпт (примерно 400 токенов)
        system_tokens = 400
        
        # Промпт пользователя
        prompt_tokens = chunker.count_tokens(prompt)
        
        # Оценка токенов чанков (примерно chunk_size * top_k)
        chunk_size = current_app.config.get('RAG_CHUNK_SIZE', 2000)
        chunks_tokens = chunk_size * top_k
        
        # Итого входных токенов
        input_tokens = system_tokens + prompt_tokens + chunks_tokens
        
        # Выходных токенов
        output_tokens = expected_output_tokens if expected_output_tokens > 0 else 600
        
        # Общее количество
        total_tokens = input_tokens + output_tokens
        
        # Стоимость (универсальный расчет для разных моделей тарификации)
        usage = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }
        cost = _calculate_cost(model_config, usage, request_count=1)
        
        return jsonify({
            'success': True,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'cost_input': cost['input'],
            'cost_output': cost['output'],
            'total_cost': cost['total'],
            'pricing_model': cost.get('pricing_model', 'per_token'),
            'model': model_id,
            'top_k': top_k
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/estimate: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка оценки: {str(e)}'
        }), 500


@ai_rag_bp.route('/index', methods=['POST'])
def index_documents():
    """
    Индексировать выбранные документы для RAG.
    
    Ожидает JSON:
    {
        "file_paths": ["path1", "path2", ...]
    }
    
    Returns:
        JSON с результатами индексации
    """
    try:
        data = request.get_json()
        
        if not data or 'file_paths' not in data:
            return jsonify({
                'success': False,
                'message': 'Не переданы file_paths'
            }), 400
        
        file_paths = data['file_paths']
        
        if not file_paths:
            return jsonify({
                'success': False,
                'message': 'Список файлов пуст'
            }), 400
        
        upload_folder = current_app.config['UPLOAD_FOLDER']
        rag_service = get_rag_service()
        
        if not rag_service.db_available:
            return jsonify({
                'success': False,
                'message': 'База данных недоступна'
            }), 503
        
        # Индексируем документы
        results = []
        total_chunks = 0
        
        for file_path in file_paths:
            success, message, stats = rag_service.index_document(
                file_path=file_path,
                upload_folder=upload_folder
            )
            
            results.append({
                'file_path': file_path,
                'success': success,
                'message': message,
                'stats': stats
            })
            
            if stats:
                total_chunks += stats.get('chunks_count', 0)
        
        # Проверяем общий успех
        all_success = all(r['success'] for r in results)
        
        return jsonify({
            'success': all_success,
            'message': f'Проиндексировано {len([r for r in results if r["success"]])} из {len(file_paths)} файлов',
            'results': results,
            'total_chunks': total_chunks
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/index: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка индексации: {str(e)}'
        }), 500


def _get_api_client(model_id: str, api_key: str, timeout: int = 90):
    """
    Создать OpenAI-совместимый клиент для указанной модели/провайдера.
    Предпочитаем определять провайдера из models.json.
    """
    import openai

    api_keys_mgr = get_api_keys_manager_multiple()

    # Пытаемся определить провайдера из конфигурации моделей
    provider = 'openai'
    try:
        cfg = _load_models_config()
        for m in cfg.get('models', []):
            if m.get('model_id') == model_id:
                provider = m.get('provider', 'openai')
                break
    except Exception:
        provider = 'openai'

    # DeepSeek
    if provider == 'deepseek' or model_id.startswith('deepseek-'):
        deepseek_key = api_keys_mgr.get_key('deepseek') or os.environ.get('DEEPSEEK_API_KEY') or api_key
        return openai.OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com", timeout=timeout)

    # Perplexity (семейство sonar: sonar, sonar-pro, sonar-reasoning, sonar-reasoning-pro, sonar-deep-research)
    if provider == 'perplexity' or model_id.startswith('sonar'):
        pplx_key = api_keys_mgr.get_key('perplexity') or os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY') or api_key
        if not pplx_key or not pplx_key.strip():
            raise RuntimeError('Perplexity API ключ не настроен. Укажите PPLX_API_KEY/PERPLEXITY_API_KEY или добавьте ключ в разделе «API ключи».')
        return openai.OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai", timeout=timeout)

    # По умолчанию OpenAI
    openai_key = api_keys_mgr.get_key('openai') or api_key
    return openai.OpenAI(api_key=openai_key, timeout=timeout)


def _perplexity_search_api(
    file_paths: List[str],
    prompt: str,
    search_params: Dict[str, Any],
    usd_rub_rate: float = None
):
    """Выполнить поиск через Perplexity Search API (без LLM, только результаты поиска)."""
    import time
    import requests
    start_time = time.time()
    
    try:
        # Получаем API ключ для Perplexity
        api_keys_mgr = get_api_keys_manager_multiple()
        pplx_key = api_keys_mgr.get_key('perplexity') or os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY')
        
        if not pplx_key:
            return jsonify({
                'success': False,
                'message': 'Perplexity API ключ не настроен'
            }), 500
        
        # Формируем запрос для Search API
        # Документация: https://docs.perplexity.ai/api-reference/search-api
        url = "https://api.perplexity.ai/v1/search"
        headers = {
            "Authorization": f"Bearer {pplx_key}",
            "Content-Type": "application/json"
        }
        
        # Базовые параметры
        payload = {
            "query": prompt,
            "max_results": search_params.get('max_results', 10)
        }
        
        # Опциональные параметры
        if search_params.get('search_domain_filter'):
            domains = search_params['search_domain_filter']
            if isinstance(domains, str):
                domains = [d.strip() for d in domains.split(',') if d.strip()]
            payload['search_domain_filter'] = domains
        
        if search_params.get('search_recency_filter'):
            payload['search_recency_filter'] = search_params['search_recency_filter']
        
        if search_params.get('search_after_date'):
            payload['search_after_date'] = search_params['search_after_date']
        
        if search_params.get('search_before_date'):
            payload['search_before_date'] = search_params['search_before_date']
        
        if search_params.get('country'):
            payload['country'] = search_params['country']
        
        if search_params.get('max_tokens_per_page'):
            payload['max_tokens_per_page'] = search_params['max_tokens_per_page']
        
        current_app.logger.info(f'Perplexity Search API запрос: {payload}')
        
        # Выполняем запрос
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if not response.ok:
            error_msg = f"Search API error: {response.status_code} - {response.text}"
            current_app.logger.error(error_msg)
            return jsonify({
                'success': False,
                'message': f'Ошибка Search API: {error_msg}'
            }), response.status_code
        
        search_data = response.json()
        
        # Форматируем результаты
        results = search_data.get('results', [])
        formatted_output = f"# Результаты поиска Perplexity\n\n**Запрос:** {prompt}\n\n"
        formatted_output += f"**Найдено результатов:** {len(results)}\n\n---\n\n"
        
        for idx, result in enumerate(results, 1):
            formatted_output += f"## {idx}. {result.get('title', 'Без названия')}\n\n"
            formatted_output += f"**URL:** {result.get('url', 'N/A')}\n\n"
            if result.get('snippet'):
                formatted_output += f"**Описание:** {result['snippet']}\n\n"
            formatted_output += "---\n\n"
        
        # Подсчёт стоимости (за запросы, не за токены)
        elapsed_time = time.time() - start_time
        
        # Загружаем конфиг для получения цены
        config = _load_models_config()
        price_per_1000 = 5.0  # Дефолт
        
        for m in config.get('models', []):
            if m['model_id'] == 'perplexity-search-api':
                price_per_1000 = m.get('price_per_1000_requests', 5.0)
                break
        
        # 1 запрос = price_per_1000 / 1000
        cost_usd = price_per_1000 / 1000
        cost_rub = cost_usd * (usd_rub_rate if usd_rub_rate else 0)
        
        metrics = {
            'model': 'perplexity-search-api',
            'requests': 1,
            'cost_usd': round(cost_usd, 4),
            'cost_rub': round(cost_rub, 2) if usd_rub_rate else 0,
            'time': round(elapsed_time, 2),
            'results_count': len(results)
        }
        
        current_app.logger.info(f'Search API выполнен за {elapsed_time:.2f}с, {len(results)} результатов')
        
        return jsonify({
            'success': True,
            'result': formatted_output,
            'metrics': metrics
        }), 200
    
    except requests.exceptions.Timeout:
        current_app.logger.exception('Search API timeout')
        return jsonify({
            'success': False,
            'message': 'Таймаут запроса к Search API'
        }), 504
    except Exception as e:
        current_app.logger.exception(f'Ошибка Search API: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка Search API: {str(e)}'
        }), 500


def _direct_analyze_without_rag(
    file_paths: List[str],
    prompt: str,
    model_id: str,
    max_output_tokens: int,
    temperature: float,
    upload_folder: str,
    usd_rub_rate: float = None,
    search_enabled: bool = False,
    search_params: Optional[Dict[str, Any]] = None
):
    """Прямой анализ без RAG - просто читаем тексты и отправляем в OpenAI."""
    import time
    start_time = time.time()
    
    try:
        import openai
        
        # Получаем API ключ через менеджер
        api_keys_mgr = get_api_keys_manager_multiple()
        api_key = api_keys_mgr.get_key('openai')
        if not api_key:
            api_key = current_app.config.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return jsonify({
                'success': False,
                'message': 'OpenAI API ключ не настроен'
            }), 500
        
        # Читаем тексты из индекса (используем функцию из ai_analysis)
        from webapp.routes.ai_analysis import _extract_text_from_index_for_files
        from webapp.services.indexing import get_index_path
        
        # Получаем путь к индексу
        index_folder = current_app.config.get('INDEX_FOLDER')
        index_path = get_index_path(index_folder) if index_folder else None
        
        combined_docs = ''
        
        if index_path and os.path.exists(index_path):
            # Извлекаем текст из индекса
            combined_docs = _extract_text_from_index_for_files(file_paths, index_path)
        
        if not combined_docs or not combined_docs.strip():
            return jsonify({
                'success': False,
                'message': 'Не удалось извлечь текст из файлов. Постройте индекс через кнопку «Построить индекс».'
            }), 400
        
        # Получаем конфигурацию модели для проверки поддержки system role и лимитов
        config = _load_models_config()
        model_config = None
        
        for m in config.get('models', []):
            if m['model_id'] == model_id:
                model_config = m
                break
        
        # Проверяем поддержку system role (o1-* модели не поддерживают)
        supports_system = True
        if model_config:
            supports_system = model_config.get('supports_system_role', True)
        
        # Получаем timeout из модели или используем глобальный
        if model_config and 'timeout' in model_config:
            timeout = model_config['timeout']
        else:
            timeout = current_app.config.get('OPENAI_TIMEOUT', 90)

        # Определяем лимит контекста модели
        def _get_context_window_tokens(mid: str, cfg: Optional[Dict[str, Any]]) -> int:
            # 1) из конфигурации, если задано > 0
            if cfg:
                try:
                    val = int(cfg.get('context_window_tokens') or 0)
                    if val > 0:
                        return val
                except Exception:
                    pass
            # 2) известные значения по умолчанию
            known: Dict[str, int] = {
                'gpt-3.5-turbo': 16385,
                'gpt-4o-mini': 128000,
                'gpt-4o': 128000,
                'gpt-4.1': 128000,
                'gpt-5': 200000,
                'deepseek-chat': 65536,
                'deepseek-reasoner': 65536,
                'sonar': 128000,
                'sonar-pro': 128000,
                'sonar-reasoning': 128000,
                'sonar-reasoning-pro': 128000,
                'sonar-deep-research': 128000,
            }
            for k, v in known.items():
                if mid.startswith(k):
                    return v
            # 3) дефолт
            return 16385

        context_window = _get_context_window_tokens(model_id, model_config)

        # Токенайзер (graceful degrade)
        try:
            import tiktoken  # type: ignore
            # Для большинства chat-моделей OpenAI подходит cl100k_base
            encoding = tiktoken.get_encoding('cl100k_base')
            def count_tokens(text: str) -> int:
                return len(encoding.encode(text))
            def truncate_by_tokens(text: str, max_tokens: int) -> str:
                if max_tokens <= 0:
                    return ''
                ids = encoding.encode(text)
                if len(ids) <= max_tokens:
                    return text
                return encoding.decode(ids[:max_tokens])
        except Exception:
            # При отсутствии tiktoken используем грубую эвристику: ~4 символа на токен
            avg_chars_per_token = 4
            def count_tokens(text: str) -> int:
                return max(1, len(text) // avg_chars_per_token)
            def truncate_by_tokens(text: str, max_tokens: int) -> str:
                if max_tokens <= 0:
                    return ''
                max_chars = max_tokens * avg_chars_per_token
                return text[:max_chars]

        # Резерв под ответ и служебные токены
        # Берём max_output_tokens, плюс запас 512 токенов под форматирование/служебные поля
        reserve_for_output = int(max_output_tokens or 0)
        safety_margin = 512

        # Оценим накладные (prompt + системное сообщение без текста документов)
        system_text = "Вы - помощник для анализа документов. Отвечайте на русском языке." if supports_system else ''
        user_prefix = "Документы:\n\n"
        user_suffix = f"\n\nЗапрос: {prompt}"
        overhead_text = (system_text + user_prefix + user_suffix) if supports_system else ("Ты - помощник для анализа документов. Отвечай на русском языке.\n\n" + user_prefix + user_suffix)
        overhead_tokens = count_tokens(overhead_text)

        allowed_doc_tokens = context_window - reserve_for_output - overhead_tokens - safety_margin
        if allowed_doc_tokens <= 0:
            # Объём явно не поместится — возвращаем понятную ошибку пользователю
            return jsonify({
                'success': False,
                'message': (
                    f'Слишком большой объём текста для выбранной модели {model_id}. '
                    f'Доступно токенов под документы: {max(0, allowed_doc_tokens)} из {context_window}. '
                    'Уменьшите число выбранных файлов или выберите модель с большим контекстом.'
                )
            }), 400

        combined_docs_trunc = truncate_by_tokens(combined_docs, allowed_doc_tokens)
        # Если усекли более чем на 5%, предупредим логом (в UI сообщим при finish_reason length)
        if len(combined_docs_trunc) < len(combined_docs) * 0.95:
            current_app.logger.info(
                f'Текст документов усечён под лимит контекста: {len(combined_docs)} -> {len(combined_docs_trunc)} символов '
                f'(allowed_doc_tokens={allowed_doc_tokens}, context_window={context_window})'
            )
        
    # Создаём клиент с учётом провайдера (OpenAI/Perplexity/DeepSeek)
        client = _get_api_client(model_id, api_key, timeout)
        
        # Для o1-* моделей используем только user role
        if supports_system:
            messages = [
                {"role": "system", "content": "Вы - помощник для анализа документов. Отвечайте на русском языке."},
                {"role": "user", "content": f"Документы:\n\n{combined_docs_trunc}\n\nЗапрос: {prompt}"}
            ]
        else:
            messages = [
                {"role": "user", "content": f"Ты - помощник для анализа документов. Отвечай на русском языке.\n\nДокументы:\n\n{combined_docs_trunc}\n\nЗапрос: {prompt}"}
            ]
        
        # Определяем параметры для новых семейств (o1, o3, o4, gpt-4.1, gpt-5)
        is_new_family = model_id.startswith(('o1', 'o3', 'o4', 'gpt-4.1', 'gpt-5'))
        is_sonar = model_id.startswith('sonar')
        
        try:
            # Новые модели используют max_completion_tokens и не принимают temperature
            if is_new_family:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    max_completion_tokens=max_output_tokens
                )
            else:
                # Для Perplexity Sonar учитываем флаг веб-поиска
                req_kwargs = {
                    'model': model_id,
                    'messages': messages,
                    'temperature': temperature,
                }
                if is_sonar and search_enabled:
                    # Поисковые параметры Perplexity передаём через extra_body (требование OpenAI SDK)
                    try:
                        from webapp.services.search.manager import normalize_search_params, apply_search_to_request
                        norm = normalize_search_params(search_params) if search_params else {}
                        apply_search_to_request(req_kwargs, norm or {})
                    except Exception:
                        # Фолбэк: минимальный набор параметров поиска
                        req_kwargs['extra_body'] = {
                            'enable_search_classifier': True,
                            'search_mode': 'web',
                            'language_preference': 'ru',
                            'web_search_options': {'search_context_size': 'low'}
                        }
                        if search_params:
                            req_kwargs['extra_body'].update(search_params)
                else:
                    if is_sonar:
                        # Переключатель выключен — гарантированно отключаем поиск через extra_body
                        req_kwargs['extra_body'] = {'disable_search': True}
                    else:
                        req_kwargs['max_tokens'] = max_output_tokens

                response = client.chat.completions.create(**req_kwargs)
        except Exception as api_err:
            error_str = str(api_err)
            current_app.logger.error(f'Ошибка API {model_id}: {error_str}', exc_info=True)
            # Дружественная обработка 401 от Perplexity (sonar): неверный/просроченный ключ
            if (model_id.startswith('sonar') and (
                '401' in error_str or 'Authorization Required' in error_str or 'AuthenticationError' in error_str or 'unauthorized' in error_str.lower()
            )):
                return jsonify({
                    'success': False,
                    'message': (
                        'Не удалось выполнить запрос к Perplexity (sonar): неверный или просроченный API ключ. '
                        'Проверьте ключ в разделе «API ключи» или задайте переменную окружения PPLX_API_KEY/PERPLEXITY_API_KEY.'
                    )
                }), 401
            
            # Обработка ошибки таймаута
            if 'timed out' in error_str.lower() or 'timeout' in error_str.lower():
                return jsonify({
                    'success': False,
                    'message': f'Запрос превышает лимит времени {timeout} сек. Попробуйте позже.'
                }), 504
            
            # Обработка ошибки превышения контекста (на случай несовпадения оценки токенов)
            if 'context_length_exceeded' in error_str or 'maximum context length' in error_str:
                # Попытка сократить текст
                current_app.logger.warning(f'Превышен лимит контекста для {model_id}, сокращаем текст')
                
                # Ещё уменьшаем допустимые токены документов в 2 раза
                reduced_tokens = max(1, allowed_doc_tokens // 2)
                combined_docs_short = truncate_by_tokens(combined_docs_trunc, reduced_tokens)
                
                if supports_system:
                    messages = [
                        {"role": "system", "content": "Вы - помощник для анализа документов. Отвечайте на русском языке."},
                        {"role": "user", "content": f"Документы (сокращённые):\n\n{combined_docs_short}\n\nЗапрос: {prompt}"}
                    ]
                else:
                    messages = [
                        {"role": "user", "content": f"Ты - помощник для анализа документов. Отвечай на русском языке.\n\nДокументы (сокращённые):\n\n{combined_docs_short}\n\nЗапрос: {prompt}"}
                    ]
                
                try:
                    # Используем те же правила для ретрая
                    if is_new_family:
                        response = client.chat.completions.create(
                            model=model_id,
                            messages=messages,
                            max_completion_tokens=max_output_tokens
                        )
                    else:
                        req_kwargs = {
                            'model': model_id,
                            'messages': messages,
                            'temperature': temperature,
                        }
                        if is_sonar and search_enabled:
                            try:
                                from webapp.services.search.manager import normalize_search_params, apply_search_to_request
                                norm = normalize_search_params(search_params) if search_params else {}
                                apply_search_to_request(req_kwargs, norm or {})
                            except Exception:
                                req_kwargs['extra_body'] = {
                                    'enable_search_classifier': True,
                                    'search_mode': 'web',
                                    'language_preference': 'ru',
                                    'web_search_options': {'search_context_size': 'low'}
                                }
                                if search_params:
                                    req_kwargs['extra_body'].update(search_params)
                        else:
                            if is_sonar:
                                req_kwargs['extra_body'] = {'disable_search': True}
                            else:
                                req_kwargs['max_tokens'] = max_output_tokens

                        response = client.chat.completions.create(**req_kwargs)
                except Exception as retry_err:
                    return jsonify({
                        'success': False,
                        'message': f'Ошибка анализа даже после сокращения текста: {str(retry_err)}'
                    }), 500

            # Обработка ограничения по токенам в минуту (TPM) — HTTP 429 rate_limit_exceeded
            elif 'rate_limit_exceeded' in error_str or 'tokens per min' in error_str or 'TPM' in error_str or 'Error code: 429' in error_str:
                try:
                    import time as _time
                    # Вычислим текущую оценку запроса
                    doc_tokens_now = count_tokens(combined_docs_trunc)
                    total_requested = overhead_tokens + doc_tokens_now + reserve_for_output

                    # Попробуем извлечь лимит/запрошено из текста
                    tpm_limit = None
                    m = re.search(r'Limit\s+(\d+)\D+Requested\s+(\d+)', error_str)
                    if m:
                        try:
                            tpm_limit = int(m.group(1))
                            requested_val = int(m.group(2))
                            current_app.logger.warning(f'TPM ограничение: limit={tpm_limit}, requested={requested_val}')
                        except Exception:
                            tpm_limit = None
                    
                    if tpm_limit and tpm_limit > 1000:
                        target_total = max(1000, int(tpm_limit * 0.9) - safety_margin)
                    else:
                        # Если не смогли распарсить — сокращаем вдвое
                        target_total = max(1000, int(total_requested * 0.5))

                    if target_total <= overhead_tokens + 64:
                        return jsonify({
                            'success': False,
                            'message': (
                                'Ограничение провайдера по токенам в минуту для модели слишком низкое для текущего объёма. '
                                'Уменьшите количество файлов, сократите промпт или попробуйте позже/выберите другую модель.'
                            )
                        }), 429

                    # Пропорционально уменьшаем токены документов и ответа
                    ratio = target_total / max(1, total_requested)
                    new_doc_token_limit = max(1, int(doc_tokens_now * ratio))
                    new_output_limit = max(64, int(reserve_for_output * ratio))

                    current_app.logger.info(
                        f'Адаптация под TPM: total_requested={total_requested} -> target_total={target_total}, '
                        f'doc_tokens {doc_tokens_now}->{new_doc_token_limit}, output {reserve_for_output}->{new_output_limit}'
                    )

                    combined_docs_tpm = truncate_by_tokens(combined_docs_trunc, new_doc_token_limit)
                    if supports_system:
                        messages = [
                            {"role": "system", "content": "Вы - помощник для анализа документов. Отвечайте на русском языке."},
                            {"role": "user", "content": f"Документы (уменьшено):\n\n{combined_docs_tpm}\n\nЗапрос: {prompt}"}
                        ]
                    else:
                        messages = [
                            {"role": "user", "content": f"Ты - помощник для анализа документов. Отвечай на русском языке.\n\nДокументы (уменьшено):\n\n{combined_docs_tpm}\n\nЗапрос: {prompt}"}
                        ]

                    # Небольшой бэк-офф перед повтором
                    _time.sleep(1)

                    if is_new_family:
                        response = client.chat.completions.create(
                            model=model_id,
                            messages=messages,
                            max_completion_tokens=new_output_limit
                        )
                    else:
                        req_kwargs = {
                            'model': model_id,
                            'messages': messages,
                            'temperature': temperature,
                        }
                        if is_sonar and search_enabled:
                            try:
                                from webapp.services.search.manager import normalize_search_params, apply_search_to_request
                                norm = normalize_search_params(search_params) if search_params else {}
                                apply_search_to_request(req_kwargs, norm or {})
                            except Exception:
                                req_kwargs['extra_body'] = {
                                    'enable_search_classifier': True,
                                    'search_mode': 'web',
                                    'language_preference': 'ru',
                                    'web_search_options': {'search_context_size': 'low'}
                                }
                                if search_params:
                                    req_kwargs['extra_body'].update(search_params)
                        else:
                            if is_sonar:
                                req_kwargs['extra_body'] = {'disable_search': True}
                            else:
                                req_kwargs['max_tokens'] = new_output_limit

                        response = client.chat.completions.create(**req_kwargs)
                except Exception as retry_rate_err:
                    return jsonify({
                        'success': False,
                        'message': (
                            'Провайдер вернул ограничение по токенам в минуту (429). '
                            'Даже после автоматического уменьшения объёма запрос не прошёл. '
                            'Попробуйте уменьшить объём документов или подождать/выбрать другую модель. '
                            f'Детали: {str(retry_rate_err)}'
                        )
                    }), 429
            else:
                return jsonify({
                    'success': False,
                    'message': f'Ошибка анализа: {error_str}'
                }), 500
        
        # Извлекаем результат
        answer = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        
        # Проверяем, был ли ответ обрезан
        if finish_reason == 'length':
            current_app.logger.warning(f'Ответ был обрезан из-за лимита max_tokens={max_output_tokens}')
            answer += '\n\n⚠️ **Примечание:** Ответ был обрезан из-за ограничения длины. Увеличьте параметр max_output_tokens для получения полного ответа.'
        
        usage = {
            'input_tokens': response.usage.prompt_tokens,
            'output_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
        
        # Вычисляем время выполнения
        duration_seconds = time.time() - start_time
        
        # Логируем использование токенов
        log_token_usage(
            model_id=model_id,
            prompt_tokens=usage['input_tokens'],
            completion_tokens=usage['output_tokens'],
            total_tokens=usage['total_tokens'],
            duration_seconds=duration_seconds,
            metadata={
                'file_count': len(file_paths),
                'prompt_length': len(prompt),
                'mode': 'direct_without_rag'
            }
        )
        
        # Вычисляем стоимость
        # Отображаемое имя модели (+ Search при активном поиске для Sonar)
        model_display = model_id
        if is_sonar and search_enabled:
            model_display = f"{model_id} + Search"

        result = {
            'answer': answer,
            'usage': usage,
            'model': model_display,
            'finish_reason': finish_reason
        }
        
        if model_config:
            # Универсальный расчет стоимости
            cost = _calculate_cost(model_config, usage, request_count=1)
            
            # Курс доллара для конвертации в рубли (пользовательский или дефолтный)
            if usd_rub_rate and usd_rub_rate > 0:
                usd_to_rub = usd_rub_rate
            else:
                usd_to_rub = current_app.config.get('USD_TO_RUB_RATE', 95.0)
            
            result['cost'] = {
                'input': cost['input'],
                'output': cost['output'],
                'total': cost['total'],
                'currency': cost['currency'],
                'pricing_model': cost.get('pricing_model', 'per_token'),
                'input_rub': round(cost['input'] * usd_to_rub, 2),
                'output_rub': round(cost['output'] * usd_to_rub, 2),
                'total_rub': round(cost['total'] * usd_to_rub, 2),
                'usd_to_rub_rate': usd_to_rub
            }
            
            # Для моделей с тарификацией по запросам добавляем количество запросов
            if cost.get('pricing_model') == 'per_request':
                result['cost']['requests_count'] = cost.get('requests_count', 1)
        
        return jsonify({
            'success': True,
            'message': 'Анализ выполнен успешно (без RAG)',
            'result': result
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка прямого анализа: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка анализа: {str(e)}'
        }), 500


@ai_rag_bp.route('/render_html', methods=['POST'])
def render_html():
    """
    Рендерит результат анализа в красиво отформатированный HTML.
    
    Ожидает JSON:
    {
        "result": {
            "answer": "текст ответа в Markdown",
            "cost": {...},
            "usage": {...},
            "model": "..."
        }
    }
    
    Returns:
        JSON с отформатированным HTML
    """
    try:
        from webapp.utils.markdown_renderer import render_analysis_result
        
        data = request.get_json()
        if not data or 'result' not in data:
            return jsonify({
                'success': False,
                'message': 'Не передан результат для рендеринга'
            }), 400
        
        result = data['result']
        html = render_analysis_result(result)
        
        return jsonify({
            'success': True,
            'html': html
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка рендеринга HTML: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка рендеринга: {str(e)}'
        }), 500


@ai_rag_bp.route('/analyze', methods=['POST'])
def analyze():
    """
    Выполнить RAG-анализ документов.
    
    Ожидает JSON:
    {
        "file_paths": ["path1", "path2"],
        "prompt": "текст промпта",
        "model_id": "gpt-4o-mini",
        "top_k": 5,
        "max_output_tokens": 600,
        "temperature": 0.3
    }
    
    Returns:
        JSON с результатом анализа
    """
    import time
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Не переданы данные'
            }), 400
        
        file_paths = data.get('file_paths', [])
        prompt = data.get('prompt', '')
        model_id = data.get('model_id', 'gpt-4o-mini')
        top_k = data.get('top_k', 5)
        max_output_tokens = data.get('max_output_tokens', 600)
        temperature = data.get('temperature', 0.3)
        usd_rub_rate = data.get('usd_rub_rate')  # Пользовательский курс USD/RUB
        
        if not file_paths:
            return jsonify({
                'success': False,
                'message': 'Не выбраны файлы для анализа'
            }), 400
        
        if not prompt:
            return jsonify({
                'success': False,
                'message': 'Не указан промпт'
            }), 400
        
        # Если включен режим поиска, передаем параметры в RAG
        search_enabled = data.get('search_enabled', False)
        search_params = data.get('search_params', {}) if search_enabled else {}
        
        if search_enabled:
            current_app.logger.info(f'RAG анализ с поиском: модель {model_id}, параметры: {search_params}')
        
        current_app.logger.info(f'RAG анализ: {len(file_paths)} файлов, модель {model_id}, Top-K={top_k}')
        
        # Получаем RAG-сервис
        upload_folder = current_app.config['UPLOAD_FOLDER']
        rag_service = get_rag_service()
        
        # Проверяем доступность БД для RAG
        if not rag_service.db_available:
            # Если БД недоступна, делаем прямой анализ без векторного поиска
            current_app.logger.warning('БД недоступна, используется прямой анализ без RAG')
            return _direct_analyze_without_rag(
                file_paths=file_paths,
                prompt=prompt,
                model_id=model_id,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                upload_folder=upload_folder,
                usd_rub_rate=usd_rub_rate,
                search_enabled=search_enabled,
                search_params=search_params
            )
        
        # Выполняем анализ с RAG
        try:
            success, message, result = rag_service.search_and_analyze(
                query=prompt,
                file_paths=file_paths,
                model=model_id,
                top_k=top_k,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                upload_folder=upload_folder,
                search_params=search_params if search_enabled else None
            )
        except Exception as rag_err:
            # При любой ошибке RAG (включая эмбеддинги) используем fallback
            current_app.logger.warning(f'Ошибка RAG, переключение на прямой анализ: {rag_err}')
            return _direct_analyze_without_rag(
                file_paths=file_paths,
                prompt=prompt,
                model_id=model_id,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                upload_folder=upload_folder,
                usd_rub_rate=usd_rub_rate,
                search_enabled=search_enabled,
                search_params=search_params
            )
        
        # Если RAG вернул ошибку, тоже используем fallback
        if not success:
            # Проверяем, нужен ли fallback
            if any(keyword in message.lower() for keyword in ['эмбеддинг', 'embedding', 'база данных недоступна', 'database']):
                current_app.logger.warning(f'Ошибка RAG/БД, переключение на прямой анализ: {message}')
                return _direct_analyze_without_rag(
                    file_paths=file_paths,
                    prompt=prompt,
                    model_id=model_id,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    upload_folder=upload_folder,
                    usd_rub_rate=usd_rub_rate
                )
            # Другие ошибки возвращаем как есть
            return jsonify({'success': False, 'message': message}), 400
        
        if success:
            current_app.logger.info(f'RAG анализ выполнен успешно: {result["usage"]}')
            
            # Вычисляем время выполнения
            duration_seconds = time.time() - start_time
            
            # Логируем использование токенов
            usage = result.get('usage', {})
            if usage:
                log_token_usage(
                    model_id=model_id,
                    prompt_tokens=usage.get('input_tokens', 0),
                    completion_tokens=usage.get('output_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                    duration_seconds=duration_seconds,
                    metadata={
                        'file_count': len(file_paths),
                        'top_k': top_k,
                        'prompt_length': len(prompt)
                    }
                )
            
            # Вычисляем стоимость
            config = _load_models_config()
            model_config = None
            
            for m in config.get('models', []):
                if m['model_id'] == model_id:
                    model_config = m
                    break
            
            if model_config:
                # Универсальный расчет стоимости
                cost = _calculate_cost(model_config, usage, request_count=1)
                
                # Курс доллара для конвертации в рубли (пользовательский или дефолтный)
                if usd_rub_rate and usd_rub_rate > 0:
                    usd_to_rub = usd_rub_rate
                else:
                    usd_to_rub = current_app.config.get('USD_TO_RUB_RATE', 95.0)
                
                result['cost'] = {
                    'input': cost['input'],
                    'output': cost['output'],
                    'total': cost['total'],
                    'currency': cost['currency'],
                    'pricing_model': cost.get('pricing_model', 'per_token'),
                    'input_rub': round(cost['input'] * usd_to_rub, 2),
                    'output_rub': round(cost['output'] * usd_to_rub, 2),
                    'total_rub': round(cost['total'] * usd_to_rub, 2),
                    'usd_to_rub_rate': usd_to_rub
                }
                
                # Для моделей с тарификацией по запросам добавляем количество запросов
                if cost.get('pricing_model') == 'per_request':
                    result['cost']['requests_count'] = cost.get('requests_count', 1)
            
            return jsonify({
                'success': True,
                'message': message,
                'result': result
            }), 200
        else:
            current_app.logger.error(f'Ошибка RAG анализа: {message}')
            return jsonify({
                'success': False,
                'message': message
            }), 500
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/analyze: {e}')
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500


@ai_rag_bp.route('/status', methods=['GET'])
def get_status():
    """
    Получить статус RAG-системы.
    
    Returns:
        JSON со статусом доступности компонентов
    """
    try:
        rag_service = get_rag_service()
        
        # Проверяем доступность БД
        db_available = rag_service.db_available
        db_stats = None
        
        if db_available:
            try:
                db_stats = rag_service.get_database_stats()
            except Exception:
                pass
        
        # Проверяем API ключ
        api_key_available = bool(rag_service.api_key)
        
        return jsonify({
            'success': True,
            'rag_enabled': current_app.config.get('RAG_ENABLED', False),
            'database_available': db_available,
            'database_stats': db_stats,
            'api_key_configured': api_key_available,
            'embeddings_model': current_app.config.get('RAG_EMBEDDING_MODEL', 'text-embedding-3-small')
        }), 200
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/status: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка получения статуса: {str(e)}'
        }), 500


@ai_rag_bp.route('/export_docx', methods=['POST'])
def export_docx():
    """
    Экспортировать результат анализа в DOCX файл.
    
    Ожидает JSON:
    {
        "result": {
            "answer": "текст ответа с markdown",
            "model": "gpt-4o-mini",
            "usage": {...},
            "cost": {...}
        }
    }
    
    Returns:
        DOCX файл для скачивания
    """
    try:
        data = request.get_json()
        
        if not data or 'result' not in data:
            return jsonify({
                'success': False,
                'message': 'Не переданы данные результата'
            }), 400
        
        result = data['result']
        answer = result.get('answer', '')
        model = result.get('model', 'неизвестная модель')
        usage = result.get('usage', {})
        cost = result.get('cost', {})
        
        if not answer:
            return jsonify({
                'success': False,
                'message': 'Нет текста для экспорта'
            }), 400
        
        # Создаём документ Word
        doc = Document()
        
        # Заголовок
        heading = doc.add_heading('Результат AI Анализа', level=1)
        heading.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Метаданные
        doc.add_paragraph()
        meta_para = doc.add_paragraph()
        meta_para.add_run('Дата: ').bold = True
        meta_para.add_run(datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
        meta_para.add_run('\n')
        
        meta_para.add_run('Модель: ').bold = True
        meta_para.add_run(model)
        meta_para.add_run('\n')
        
        if cost:
            meta_para.add_run('Стоимость: ').bold = True
            meta_para.add_run(f"${cost.get('total', 0):.6f} ")
            meta_para.add_run(f"(вход: ${cost.get('input', 0):.6f}, выход: ${cost.get('output', 0):.6f})")
            meta_para.add_run('\n')
            
            # Стоимость в рублях
            if 'total_rub' in cost:
                meta_para.add_run('В рублях: ').bold = True
                meta_para.add_run(f"₽{cost.get('total_rub', 0):.2f} ")
                meta_para.add_run(f"(вход: ₽{cost.get('input_rub', 0):.2f}, выход: ₽{cost.get('output_rub', 0):.2f}) ")
                meta_para.add_run(f"по курсу ${cost.get('usd_to_rub_rate', 95.0):.2f}")
                meta_para.add_run('\n')
        
        if usage:
            meta_para.add_run('Токены: ').bold = True
            meta_para.add_run(f"{usage.get('total_tokens', 0)} ")
            meta_para.add_run(f"(вход: {usage.get('input_tokens', 0)}, выход: {usage.get('output_tokens', 0)})")
        
        # Разделитель
        doc.add_paragraph('_' * 80)
        doc.add_paragraph()
        
        # Обрабатываем Markdown текст и добавляем в документ
        _add_markdown_to_docx(doc, answer)
        
        # Сохраняем в память
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'ai_analysis_{timestamp}.docx'
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_rag/export_docx: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка экспорта DOCX: {str(e)}'
        }), 500


def _add_markdown_to_docx(doc: Document, markdown_text: str) -> None:
    """
    Добавить Markdown текст в документ DOCX с базовым форматированием.
    
    Поддерживаемые элементы:
    - Заголовки (# ## ###)
    - Жирный текст (**text**)
    - Курсив (*text*)
    - Списки (- item, * item)
    - Нумерованные списки (1. item)
    - Код (`code`)
    - Блоки кода (```code```)
    """
    lines = markdown_text.split('\n')
    in_code_block = False
    code_block_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Блок кода
        if line.strip().startswith('```'):
            if in_code_block:
                # Конец блока кода
                if code_block_lines:
                    code_para = doc.add_paragraph('\n'.join(code_block_lines))
                    code_para.style = 'No Spacing'
                    for run in code_para.runs:
                        run.font.name = 'Courier New'
                        run.font.size = Pt(9)
                        run.font.color.rgb = RGBColor(0, 0, 0)
                code_block_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue
        
        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue
        
        # Пустая строка
        if not line.strip():
            doc.add_paragraph()
            i += 1
            continue
        
        # Заголовки
        if line.startswith('# '):
            doc.add_heading(line[2:].strip(), level=1)
            i += 1
            continue
        elif line.startswith('## '):
            doc.add_heading(line[3:].strip(), level=2)
            i += 1
            continue
        elif line.startswith('### '):
            doc.add_heading(line[4:].strip(), level=3)
            i += 1
            continue
        
        # Списки
        if line.strip().startswith(('- ', '* ')):
            para = doc.add_paragraph(style='List Bullet')
            _add_formatted_text(para, line.strip()[2:])
            i += 1
            continue
        
        # Нумерованные списки
        if re.match(r'^\d+\.\s', line.strip()):
            text = re.sub(r'^\d+\.\s+', '', line.strip())
            para = doc.add_paragraph(style='List Number')
            _add_formatted_text(para, text)
            i += 1
            continue
        
        # Обычный параграф
        para = doc.add_paragraph()
        _add_formatted_text(para, line)
        i += 1


def _add_formatted_text(paragraph, text: str) -> None:
    """
    Добавить текст с форматированием (жирный, курсив, код, ссылки) в параграф.
    """
    # Сначала обрабатываем ссылки [text](url)
    link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    parts = re.split(f'({link_pattern})', text)
    
    i = 0
    while i < len(parts):
        part = parts[i]
        
        # Проверяем, является ли это ссылкой
        link_match = re.match(link_pattern, part)
        if link_match:
            link_text = link_match.group(1)
            link_url = link_match.group(2)
            _add_hyperlink(paragraph, link_url, link_text)
            i += 1
            continue
        
        # Обрабатываем инлайн-код `code`
        code_parts = re.split(r'(`[^`]+`)', part)
        
        for code_part in code_parts:
            if code_part.startswith('`') and code_part.endswith('`'):
                # Инлайн-код
                run = paragraph.add_run(code_part[1:-1])
                run.font.name = 'Courier New'
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(200, 0, 0)
            else:
                # Обрабатываем жирный текст и курсив
                _add_bold_italic_text(paragraph, code_part)
        
        i += 1


def _add_hyperlink(paragraph, url: str, text: str) -> None:
    """
    Добавить кликабельную гиперссылку в параграф.
    
    Args:
        paragraph: Параграф документа DOCX
        url: URL ссылки
        text: Текст ссылки
    """
    # Создаём элемент гиперссылки
    part = paragraph.part
    r_id = part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)
    
    # Создаём XML элемент гиперссылки
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)
    
    # Создаём новый run для текста ссылки
    new_run = OxmlElement('w:r')
    
    # Добавляем свойства run (цвет и подчёркивание для ссылки)
    rPr = OxmlElement('w:rPr')
    
    # Цвет ссылки (синий)
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0563C1')
    rPr.append(color)
    
    # Подчёркивание
    u = OxmlElement('w:u')
    u.set(qn('w:val'), 'single')
    rPr.append(u)
    
    new_run.append(rPr)
    
    # Добавляем текст
    text_elem = OxmlElement('w:t')
    text_elem.text = text
    new_run.append(text_elem)
    
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _add_bold_italic_text(paragraph, text: str) -> None:
    """
    Добавить текст с жирным и курсивом в параграф.
    """
    # Сначала обрабатываем жирный текст **text**
    bold_parts = re.split(r'(\*\*[^*]+\*\*)', text)
    
    for bold_part in bold_parts:
        if bold_part.startswith('**') and bold_part.endswith('**'):
            # Жирный текст
            run = paragraph.add_run(bold_part[2:-2])
            run.bold = True
        else:
            # Обрабатываем курсив *text*
            italic_parts = re.split(r'(\*[^*]+\*)', bold_part)
            for italic_part in italic_parts:
                if italic_part.startswith('*') and italic_part.endswith('*') and not italic_part.startswith('**'):
                    run = paragraph.add_run(italic_part[1:-1])
                    run.italic = True
                else:
                    # Обычный текст
                    if italic_part:
                        paragraph.add_run(italic_part)


# ============================================================================
# РОУТЫ ДЛЯ УЧЁТА ТОКЕНОВ
# ============================================================================

@ai_rag_bp.route('/token_report')
def token_report():
    """Страница с отчётом по использованию токенов"""
    return render_template('token_report.html')


@ai_rag_bp.route('/token_stats', methods=['GET'])
def token_stats():
    """
    Получить статистику использования токенов.
    
    Query параметры:
        start_date: Начальная дата (YYYY-MM-DD)
        end_date: Конечная дата (YYYY-MM-DD)
        model_id: Фильтр по модели
        period: Предустановленный период ('current_month', 'all_time')
    
    Returns:
        JSON со статистикой по моделям
    """
    try:
        period = request.args.get('period', 'all_time')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        model_id = request.args.get('model_id')
        
        # Предустановленные периоды
        if period == 'current_month':
            stats = get_current_month_stats()
        elif period == 'all_time':
            stats = get_all_time_stats()
        else:
            # Пользовательский период
            stats = get_token_stats(
                start_date=start_date,
                end_date=end_date,
                model_id=model_id
            )
        
        return jsonify(stats), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка получения статистики токенов: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
