"""Blueprint для RAG-анализа документов."""
import os
import json
from flask import Blueprint, request, jsonify, current_app
from typing import List, Dict, Any, Optional

from webapp.services.rag_service import get_rag_service
from webapp.services.chunking import TextChunker


ai_rag_bp = Blueprint('ai_rag', __name__, url_prefix='/ai_rag')


def _load_models_config() -> Dict[str, Any]:
    """Загрузить конфигурацию моделей из файла."""
    models_file = current_app.config.get('RAG_MODELS_FILE')
    
    if not models_file or not os.path.exists(models_file):
        # Дефолтная конфигурация
        return {
            'models': [
                {
                    'model_id': 'gpt-4o-mini',
                    'display_name': 'GPT-4o Mini',
                    'context_window_tokens': 128000,
                    'price_input_per_1m': 0.0,
                    'price_output_per_1m': 0.0,
                    'enabled': True
                }
            ],
            'default_model': 'gpt-4o-mini'
        }
    
    try:
        with open(models_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f'Ошибка загрузки models.json: {e}')
        return {'models': [], 'default_model': 'gpt-4o-mini'}


def _save_models_config(config: Dict[str, Any]):
    """Сохранить конфигурацию моделей в файл."""
    models_file = current_app.config.get('RAG_MODELS_FILE')
    
    if not models_file:
        return
    
    try:
        # Создаём директорию если нужно
        os.makedirs(os.path.dirname(models_file), exist_ok=True)
        
        with open(models_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        current_app.logger.error(f'Ошибка сохранения models.json: {e}')


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
        
        if not rag_service.db_available:
            return jsonify({
                'success': False,
                'message': 'База данных недоступна'
            }), 503
        
        # Выполняем анализ
        success, message, result = rag_service.search_and_analyze(
            query=prompt,
            file_paths=file_paths,
            model=model_id,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            upload_folder=upload_folder
        )
        
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
