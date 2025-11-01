"""Blueprint для управления множественными API ключами"""
from flask import Blueprint, request, jsonify, render_template, current_app
from utils.api_keys_manager_multiple import get_api_keys_manager_multiple

api_keys_new_bp = Blueprint('api_keys_new', __name__, url_prefix='/api_keys')


@api_keys_new_bp.route('/manage')
def manage_page():
    """Страница управления API ключами"""
    return render_template('api_keys_manager_new.html')


@api_keys_new_bp.route('/list_all', methods=['GET'])
def list_all_keys():
    """Получить список всех ключей (множественные)"""
    try:
        manager = get_api_keys_manager_multiple()
        result = manager.list_all_keys()
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(f'Ошибка получения списка ключей: {e}')
        return jsonify({
            'success': False,
            'error': str(e),
            'keys': []
        }), 500


@api_keys_new_bp.route('/add', methods=['POST'])
def add_key():
    """
    Добавить новый API ключ
    
    Ожидает JSON:
    {
        "provider": "openai" | "deepseek" | "perplexity",
        "api_key": "sk-...",
        "models_count": 68 (опционально)
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Не переданы данные'
            }), 400
        
        provider = data.get('provider')
        api_key = data.get('api_key')
        models_count = data.get('models_count', 0)
        available_models = data.get('available_models', [])
        
        if not provider or not api_key:
            return jsonify({
                'success': False,
                'error': 'Не указан provider или api_key'
            }), 400
        
        manager = get_api_keys_manager_multiple()
        result = manager.add_key(provider, api_key, models_count, available_models)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка добавления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/set_primary', methods=['PUT'])
def set_primary():
    """
    Установить ключ как основной
    
    Ожидает JSON:
    {
        "provider": "openai",
        "key_id": "uuid"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Не переданы данные'
            }), 400
        
        provider = data.get('provider')
        key_id = data.get('key_id')
        
        if not provider or not key_id:
            return jsonify({
                'success': False,
                'error': 'Не указан provider или key_id'
            }), 400
        
        manager = get_api_keys_manager_multiple()
        result = manager.set_primary_key(provider, key_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка установки основного ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/delete/<provider>/<key_id>', methods=['DELETE'])
def delete_key(provider: str, key_id: str):
    """Удалить API ключ"""
    try:
        manager = get_api_keys_manager_multiple()
        result = manager.delete_key(provider, key_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка удаления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Эндпоинты для валидации (используем старый менеджер)
@api_keys_new_bp.route('/validate', methods=['POST'])
def validate_key():
    """
    Проверить валидность API ключа
    
    Ожидает JSON:
    {
        "provider": "openai" | "deepseek" | "perplexity",
        "api_key": "sk-..." | "pplx-..."
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Не переданы данные'
            }), 400
        
        provider = data.get('provider')
        api_key = data.get('api_key')
        
        if not provider or not api_key:
            return jsonify({
                'success': False,
                'error': 'Не указан provider или api_key'
            }), 400
        
        # Используем новый менеджер для валидации
        manager = get_api_keys_manager_multiple()
        success, result = manager.validate_key(provider, api_key)
        
        if success:
            return jsonify({
                'success': True,
                **result
            }), 200
        else:
            return jsonify({
                'success': False,
                **result
            }), 400
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка валидации ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/used_models', methods=['GET'])
def get_used_models():
    """Получить список моделей, которые используются в программе"""
    try:
        import json
        import os
        
        models_file = current_app.config.get('RAG_MODELS_FILE')
        if not models_file or not os.path.exists(models_file):
            return jsonify({
                'success': True,
                'models': []
            }), 200
        
        with open(models_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        models = data.get('models', [])
        # Берём только ID моделей
        used_model_ids = [m['model_id'] for m in models if m.get('enabled', True)]
        
        return jsonify({
            'success': True,
            'models': used_model_ids
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка получения используемых моделей: {e}')
        return jsonify({
            'success': True,
            'models': []  # Возвращаем пустой список при ошибке
        }), 200


@api_keys_new_bp.route('/refresh_all', methods=['POST'])
def refresh_all_keys():
    """
    Актуализировать все ключи (перевалидировать и обновить список моделей)
    """
    try:
        manager = get_api_keys_manager_multiple()
        
        # Получаем все ключи
        result = manager.list_all_keys()
        if not result['success']:
            return jsonify(result), 500
        
        all_keys = result['keys']
        updated_count = 0
        valid_count = 0
        invalid_count = 0
        errors = []
        
        for key_data in all_keys:
            provider = key_data['provider']
            key_id = key_data['key_id']
            api_key = key_data['api_key']
            provider_name = 'OpenAI' if provider == 'openai' else 'DeepSeek'
            masked_key = api_key[:5] + '***' + api_key[-4:] if len(api_key) > 10 else '***'
            
            # Валидируем ключ
            success, validation_result = manager.validate_key(provider, api_key)
            
            if success:
                status = 'valid'
                models = validation_result.get('models', [])
                models_count = len(models)
                valid_count += 1
            else:
                status = 'invalid'
                models = []
                models_count = 0
                invalid_count += 1
                error_msg = validation_result.get('error', 'Неизвестная ошибка')
                errors.append({
                    'provider': provider_name,
                    'key': masked_key,
                    'error': error_msg
                })
            
            # Обновляем информацию
            update_result = manager.update_key_info(
                provider, 
                key_id, 
                status, 
                models_count, 
                models
            )
            
            if update_result['success']:
                updated_count += 1
        
        current_app.logger.info(f"Актуализировано {updated_count} из {len(all_keys)} ключей. Валидных: {valid_count}, Невалидных: {invalid_count}")
        
        has_errors = invalid_count > 0
        
        return jsonify({
            'success': not has_errors,  # False если есть невалидные ключи
            'message': f'Актуализировано {updated_count} ключей' if not has_errors else f'Обнаружены проблемы с {invalid_count} ключами',
            'updated_count': updated_count,
            'total_count': len(all_keys),
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'errors': errors
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка актуализации ключей: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
