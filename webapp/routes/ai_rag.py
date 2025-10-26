"""Blueprint для RAG-анализа документов."""
import os
import json
from flask import Blueprint, request, jsonify, current_app
from typing import List, Dict, Any, Optional

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

        normalized_models.append({
            'model_id': model_id,
            'display_name': display_name,
            'context_window_tokens': int(context_window) if isinstance(context_window, (int, float)) else 0,
            'price_input_per_1m': float(price_in) if price_in is not None else 0.0,
            'price_output_per_1m': float(price_out) if price_out is not None else 0.0,
            'enabled': bool(enabled),
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
        client = OpenAI(api_key=api_key)
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


@ai_rag_bp.route('/models', methods=['POST'])
def update_model_prices():
    """
    Обновить цены для модели.
    
    Ожидает JSON:
    {
        "model_id": "gpt-4o-mini",
        "price_input_per_1m": 0.15,
        "price_output_per_1m": 0.60
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
        
        # Загружаем конфигурацию
        config = _load_models_config()
        
        # Находим модель и обновляем цены
        found = False
        for model in config.get('models', []):
            if model['model_id'] == model_id:
                if price_input is not None:
                    model['price_input_per_1m'] = float(price_input)
                if price_output is not None:
                    model['price_output_per_1m'] = float(price_output)
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
            'message': 'Цены обновлены'
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
        
        # Читаем тексты из файлов (используем функцию из ai_analysis)
        from webapp.routes.ai_analysis import _extract_text_from_files
        
        combined_docs = _extract_text_from_files(file_paths, upload_folder)
        
        if not combined_docs or not combined_docs.strip():
            return jsonify({
                'success': False,
                'message': 'Не удалось извлечь текст из файлов'
            }), 400
        
        # Формируем запрос к OpenAI
        client = openai.OpenAI(api_key=api_key)
        
        messages = [
            {"role": "system", "content": "Вы - помощник для анализа документов. Отвечайте на русском языке."},
            {"role": "user", "content": f"Документы:\n\n{combined_docs}\n\nЗапрос: {prompt}"}
        ]
        
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_output_tokens,
            temperature=temperature
        )
        
        # Извлекаем результат
        answer = response.choices[0].message.content
        usage = {
            'input_tokens': response.usage.prompt_tokens,
            'output_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
        
        # Вычисляем стоимость
        config = _load_models_config()
        model_config = None
        
        for m in config.get('models', []):
            if m['model_id'] == model_id:
                model_config = m
                break
        
        result = {
            'answer': answer,
            'usage': usage,
            'model': model_id
        }
        
        if model_config:
            price_input = model_config.get('price_input_per_1m', 0.0)
            price_output = model_config.get('price_output_per_1m', 0.0)
            
            cost_input = (usage['input_tokens'] / 1_000_000) * price_input
            cost_output = (usage['output_tokens'] / 1_000_000) * price_output
            total_cost = cost_input + cost_output
            
            result['cost'] = {
                'input': round(cost_input, 4),
                'output': round(cost_output, 4),
                'total': round(total_cost, 4),
                'currency': 'USD'
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
            if 'эмбеддинг' in message.lower() or 'embedding' in message.lower():
                current_app.logger.warning(f'Ошибка эмбеддинга в RAG, переключение на прямой анализ: {message}')
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
