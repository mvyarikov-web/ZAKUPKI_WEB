"""Blueprint для RAG-анализа документов."""
import os
import json
import re
import io
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.shared import OxmlElement
from docx.oxml.ns import qn

from webapp.services.rag_service import get_rag_service
from webapp.services.chunking import TextChunker


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

        normalized_models.append({
            'model_id': model_id,
            'display_name': display_name,
            'description': description,
            'context_window_tokens': int(context_window) if isinstance(context_window, (int, float)) else 0,
            'price_input_per_1m': float(price_in) if price_in is not None else 0.0,
            'price_output_per_1m': float(price_out) if price_out is not None else 0.0,
            'enabled': bool(enabled),
            'timeout': int(timeout) if isinstance(timeout, (int, float)) else 30,
            'supports_system_role': bool(supports_system_role),
        })

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

    try:
        # Создаём директорию если нужно
        dir_path = os.path.dirname(models_file)
        os.makedirs(dir_path, exist_ok=True)

        # Атомарная запись: пишем во временный файл в той же директории и заменяем
        tmp_path = models_file + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, models_file)
    except Exception as e:
        current_app.logger.error(f'Ошибка сохранения models.json: {e}')


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
        
        # Стоимость
        price_input = model_config.get('price_input_per_1m', 0.0)
        price_output = model_config.get('price_output_per_1m', 0.0)
        
        cost_input = (input_tokens / 1_000_000) * price_input
        cost_output = (output_tokens / 1_000_000) * price_output
        total_cost = cost_input + cost_output
        
        return jsonify({
            'success': True,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'cost_input': round(cost_input, 4),
            'cost_output': round(cost_output, 4),
            'total_cost': round(total_cost, 4),
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


def _direct_analyze_without_rag(
    file_paths: List[str],
    prompt: str,
    model_id: str,
    max_output_tokens: int,
    temperature: float,
    upload_folder: str
):
    """Прямой анализ без RAG - просто читаем тексты и отправляем в OpenAI."""
    try:
        import openai
        
        # Получаем API ключ
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
        
        # Получаем конфигурацию модели для проверки поддержки system role
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
        
        client = openai.OpenAI(api_key=api_key, timeout=timeout)
        
        # Для o1-* моделей используем только user role
        if supports_system:
            messages = [
                {"role": "system", "content": "Вы - помощник для анализа документов. Отвечайте на русском языке."},
                {"role": "user", "content": f"Документы:\n\n{combined_docs}\n\nЗапрос: {prompt}"}
            ]
        else:
            messages = [
                {"role": "user", "content": f"Ты - помощник для анализа документов. Отвечай на русском языке.\n\nДокументы:\n\n{combined_docs}\n\nЗапрос: {prompt}"}
            ]
        
        # Определяем параметры для новых семейств (o1, o3, o4, gpt-4.1, gpt-5)
        is_new_family = model_id.startswith(('o1', 'o3', 'o4', 'gpt-4.1', 'gpt-5'))
        
        try:
            # Новые модели используют max_completion_tokens и не принимают temperature
            if is_new_family:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    max_completion_tokens=max_output_tokens
                )
            else:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    max_tokens=max_output_tokens,
                    temperature=temperature
                )
        except Exception as api_err:
            error_str = str(api_err)
            
            # Обработка ошибки таймаута
            if 'timed out' in error_str.lower() or 'timeout' in error_str.lower():
                return jsonify({
                    'success': False,
                    'message': f'Запрос превышает лимит времени {timeout} сек. Попробуйте позже.'
                }), 504
            
            # Обработка ошибки превышения контекста
            if 'context_length_exceeded' in error_str or 'maximum context length' in error_str:
                # Попытка сократить текст
                current_app.logger.warning(f'Превышен лимит контекста для {model_id}, сокращаем текст')
                
                # Берем только первую половину текста
                combined_docs_short = combined_docs[:len(combined_docs)//2]
                
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
                        response = client.chat.completions.create(
                            model=model_id,
                            messages=messages,
                            max_tokens=max_output_tokens,
                            temperature=temperature
                        )
                except Exception as retry_err:
                    return jsonify({
                        'success': False,
                        'message': f'Ошибка анализа даже после сокращения текста: {str(retry_err)}'
                    }), 500
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
        
        # Вычисляем стоимость
        result = {
            'answer': answer,
            'usage': usage,
            'model': model_id,
            'finish_reason': finish_reason
        }
        
        if model_config:
            price_input = model_config.get('price_input_per_1m', 0.0)
            price_output = model_config.get('price_output_per_1m', 0.0)
            
            cost_input = (usage['input_tokens'] / 1_000_000) * price_input
            cost_output = (usage['output_tokens'] / 1_000_000) * price_output
            total_cost = cost_input + cost_output
            
            # Курс доллара для конвертации в рубли
            usd_to_rub = current_app.config.get('USD_TO_RUB_RATE', 95.0)
            
            result['cost'] = {
                'input': round(cost_input, 6),
                'output': round(cost_output, 6),
                'total': round(total_cost, 6),
                'currency': 'USD',
                'input_rub': round(cost_input * usd_to_rub, 2),
                'output_rub': round(cost_output * usd_to_rub, 2),
                'total_rub': round(total_cost * usd_to_rub, 2),
                'usd_to_rub_rate': usd_to_rub
            }
        
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
                upload_folder=upload_folder
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
                upload_folder=upload_folder
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
                upload_folder=upload_folder
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
                    upload_folder=upload_folder
                )
            # Другие ошибки возвращаем как есть
            return jsonify({'success': False, 'message': message}), 400
        
        if success:
            current_app.logger.info(f'RAG анализ выполнен успешно: {result["usage"]}')
            
            # Вычисляем стоимость
            config = _load_models_config()
            model_config = None
            
            for m in config.get('models', []):
                if m['model_id'] == model_id:
                    model_config = m
                    break
            
            if model_config:
                usage = result['usage']
                price_input = model_config.get('price_input_per_1m', 0.0)
                price_output = model_config.get('price_output_per_1m', 0.0)
                
                cost_input = (usage['input_tokens'] / 1_000_000) * price_input
                cost_output = (usage['output_tokens'] / 1_000_000) * price_output
                total_cost = cost_input + cost_output
                
                result['cost'] = {
                    'input': round(cost_input, 4),
                    'output': round(cost_output, 4),
                    'total': round(total_cost, 4),
                    'currency': 'руб/USD'  # Зависит от введённых цен
                }
            
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
