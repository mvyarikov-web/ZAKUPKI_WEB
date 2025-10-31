"""Blueprint для управления API ключами"""
from flask import Blueprint, request, jsonify, render_template, current_app
from utils.api_keys_manager import get_api_keys_manager

api_keys_bp = Blueprint('api_keys', __name__, url_prefix='/api_keys')


@api_keys_bp.route('/manage')
def manage_page():
    """Страница управления API ключами"""
    return render_template('api_keys_manager.html')


@api_keys_bp.route('/list', methods=['GET'])
def list_keys():
    """Получить список всех провайдеров и их статусов"""
    try:
        manager = get_api_keys_manager()
        result = manager.list_keys()
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(f'Ошибка получения списка ключей: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_bp.route('/save', methods=['POST'])
def save_key():
    """
    Сохранить API ключ для провайдера
    
    Ожидает JSON:
    {
        "provider": "openai" или "deepseek",
        "api_key": "sk-..."
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
        
        manager = get_api_keys_manager()
        result = manager.save_key(provider, api_key)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка сохранения ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_bp.route('/validate', methods=['POST'])
def validate_key():
    """
    Проверить валидность API ключа и получить доступные модели
    
    Ожидает JSON:
    {
        "provider": "openai" или "deepseek",
        "api_key": "sk-..." (опционально, если не указан - берётся сохранённый)
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
        api_key = data.get('api_key')  # Может быть None
        
        if not provider:
            return jsonify({
                'success': False,
                'error': 'Не указан provider'
            }), 400
        
        manager = get_api_keys_manager()
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


@api_keys_bp.route('/delete/<provider>', methods=['DELETE'])
def delete_key(provider: str):
    """Удалить API ключ провайдера"""
    try:
        manager = get_api_keys_manager()
        result = manager.delete_key(provider)
        
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
