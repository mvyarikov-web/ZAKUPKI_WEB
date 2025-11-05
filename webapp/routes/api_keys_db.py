"""Blueprint для управления API ключами через БД"""
from flask import Blueprint, request, jsonify, render_template, g
from webapp.services.api_keys_service import APIKeysService
from webapp.middleware.auth_middleware import require_auth
from webapp.db.base import SessionLocal
import logging

logger = logging.getLogger(__name__)

api_keys_new_bp = Blueprint('api_keys_new', __name__, url_prefix='/api_keys')


@api_keys_new_bp.route('/manage')
def manage_page():
    """Страница управления API ключами
    
    Примечание: Авторизация проверяется на клиенте через auth.js,
    так как это HTML-страница, а не API эндпоинт.
    """
    return render_template('api_keys_manager_new.html')


@api_keys_new_bp.route('/list_all', methods=['GET'])
@require_auth
def list_all_keys():
    """Получить список всех ключей пользователя"""
    try:
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        keys_info = service.list_keys_info(user_id)
        
        return jsonify({
            'success': True,
            'keys': keys_info
        }), 200
    except Exception as e:
        logger.exception(f'Ошибка получения списка ключей: {e}')
        return jsonify({
            'success': False,
            'error': str(e),
            'keys': []
        }), 500


@api_keys_new_bp.route('/add', methods=['POST'])
@require_auth
def add_key():
    """
    Добавить новый API ключ
    
    Ожидает JSON:
    {
        "provider": "openai" | "deepseek" | "perplexity",
        "api_key": "sk-...",
        "is_shared": false (опционально)
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
        is_shared = data.get('is_shared', False)
        
        if not provider or not api_key:
            return jsonify({
                'success': False,
                'error': 'Не указан provider или api_key'
            }), 400
        
        if provider not in ['openai', 'deepseek', 'perplexity']:
            return jsonify({
                'success': False,
                'error': f'Неподдерживаемый провайдер: {provider}'
            }), 400
        
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        # Проверяем, есть ли уже ключ для этого провайдера
        if service.has_key(user_id, provider):
            # Обновляем существующий
            service.update_key(user_id, provider, api_key)
            message = f'Ключ {provider} обновлён'
        else:
            # Добавляем новый
            service.add_key(user_id, provider, api_key, is_shared)
            message = f'Ключ {provider} добавлен'
        
        return jsonify({
            'success': True,
            'message': message,
            'provider': provider
        }), 200
            
    except Exception as e:
        logger.exception(f'Ошибка добавления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/delete/<provider>', methods=['DELETE'])
@require_auth
def delete_key(provider: str):
    """Удалить API ключ пользователя для провайдера"""
    try:
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        success = service.delete_key(user_id, provider)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Ключ {provider} удалён'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Ключ не найден'
            }), 404
            
    except Exception as e:
        logger.exception(f'Ошибка удаления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/delete/<provider>/<key_id>', methods=['DELETE'])
@require_auth
def delete_key_combined(provider: str, key_id: str):
    """Удалить API ключ пользователя по провайдеру и ID (для совместимости с frontend)"""
    try:
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        # Преобразуем key_id в int
        try:
            key_id_int = int(key_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Неверный формат ID ключа'
            }), 400
        
        success = service.delete_key_by_id(user_id, key_id_int)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Ключ {provider} (ID={key_id}) удалён'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Ключ не найден или не принадлежит пользователю'
            }), 404
            
    except Exception as e:
        logger.exception(f'Ошибка удаления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/delete_by_id/<int:key_id>', methods=['DELETE'])
@require_auth
def delete_key_by_id(key_id: int):
    """Удалить API ключ по ID"""
    try:
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        success = service.delete_key_by_id(user_id, key_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Ключ ID={key_id} удалён'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Ключ не найден или не принадлежит пользователю'
            }), 404
            
    except Exception as e:
        logger.exception(f'Ошибка удаления ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_keys_new_bp.route('/get/<provider>', methods=['GET'])
@require_auth
def get_key(provider: str):
    """Получить API ключ для провайдера (расшифрованный)"""
    try:
        user_id = g.user.id
        db_session = SessionLocal()
        service = APIKeysService(db_session)
        
        api_key = service.get_key(user_id, provider)
        
        if api_key:
            return jsonify({
                'success': True,
                'provider': provider,
                'api_key': api_key
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Ключ не найден'
            }), 404
            
    except Exception as e:
        logger.exception(f'Ошибка получения ключа: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
