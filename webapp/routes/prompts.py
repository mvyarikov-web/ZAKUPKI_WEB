"""
API для работы с промптами.
"""

from flask import Blueprint, request, jsonify, g

from webapp.db.base import get_db
from webapp.services.prompt_service import PromptService
from webapp.routes.auth import require_auth

# Blueprint для промптов
prompts_bp = Blueprint('prompts', __name__, url_prefix='/prompts')


@prompts_bp.route('/list', methods=['GET'])
@require_auth
def list_prompts():
    """Получить список промптов пользователя.
    
    Query params:
        include_shared: (bool) включать ли общие промпты (по умолчанию True)
    
    Returns:
        JSON: {"success": true, "prompts": [...]}
    """
    user_id = g.user.id
    include_shared = request.args.get('include_shared', 'true').lower() == 'true'
    
    db = next(get_db())
    try:
        service = PromptService(db)
        prompts = service.get_user_prompts(user_id, include_shared)
        return jsonify({
            'success': True,
            'prompts': prompts
        })
    finally:
        db.close()


@prompts_bp.route('/<int:prompt_id>', methods=['GET'])
@require_auth
def get_prompt(prompt_id: int):
    """Получить промпт по ID.
    
    Returns:
        JSON: {"success": true, "prompt": {...}}
    """
    user_id = g.user.id
    
    db = next(get_db())
    try:
        service = PromptService(db)
        prompt = service.get_prompt_by_id(prompt_id)
        
        if not prompt:
            return jsonify({
                'success': False,
                'error': 'Промпт не найден'
            }), 404
        
        # Проверяем права доступа
        if prompt['user_id'] != user_id and not prompt['is_shared']:
            return jsonify({
                'success': False,
                'error': 'Доступ запрещен'
            }), 403
        
        return jsonify({
            'success': True,
            'prompt': prompt
        })
    finally:
        db.close()


@prompts_bp.route('/create', methods=['POST'])
@require_auth
def create_prompt():
    """Создать новый промпт.
    
    Body:
        {
            "name": "Название промпта",
            "content": "Текст промпта",
            "is_shared": false  // optional
        }
    
    Returns:
        JSON: {"success": true, "prompt": {...}}
    """
    user_id = g.user.id
    data = request.get_json()
    
    # Валидация
    if not data or 'name' not in data or 'content' not in data:
        return jsonify({
            'success': False,
            'error': 'Необходимо указать name и content'
        }), 400
    
    name = data['name'].strip()
    content = data['content'].strip()
    is_shared = data.get('is_shared', False)
    
    if not name:
        return jsonify({
            'success': False,
            'error': 'Название промпта не может быть пустым'
        }), 400
    
    if not content:
        return jsonify({
            'success': False,
            'error': 'Содержимое промпта не может быть пустым'
        }), 400
    
    db = next(get_db())
    try:
        service = PromptService(db)
        prompt = service.create_prompt(user_id, name, content, is_shared)
        
        return jsonify({
            'success': True,
            'prompt': prompt
        }), 201
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    finally:
        db.close()


@prompts_bp.route('/<int:prompt_id>', methods=['PUT'])
@require_auth
def update_prompt(prompt_id: int):
    """Обновить промпт.
    
    Body:
        {
            "name": "Новое название",  // optional
            "content": "Новый текст",  // optional
            "is_shared": true  // optional
        }
    
    Returns:
        JSON: {"success": true, "prompt": {...}}
    """
    user_id = g.user.id
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'error': 'Необходимо указать данные для обновления'
        }), 400
    
    # Фильтруем только разрешенные поля
    allowed_fields = {'name', 'content', 'is_shared'}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        return jsonify({
            'success': False,
            'error': 'Не указаны поля для обновления'
        }), 400
    
    db = next(get_db())
    try:
        service = PromptService(db)
        prompt = service.update_prompt(prompt_id, user_id, **update_data)
        
        if not prompt:
            return jsonify({
                'success': False,
                'error': 'Промпт не найден или у вас нет прав для его изменения'
            }), 404
        
        return jsonify({
            'success': True,
            'prompt': prompt
        })
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    finally:
        db.close()


@prompts_bp.route('/<int:prompt_id>', methods=['DELETE'])
@require_auth
def delete_prompt(prompt_id: int):
    """Удалить промпт.
    
    Returns:
        JSON: {"success": true}
    """
    user_id = g.user.id
    
    db = next(get_db())
    try:
        service = PromptService(db)
        deleted = service.delete_prompt(prompt_id, user_id)
        
        if not deleted:
            return jsonify({
                'success': False,
                'error': 'Промпт не найден или у вас нет прав для его удаления'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Промпт успешно удален'
        })
    finally:
        db.close()


@prompts_bp.route('/shared', methods=['GET'])
def list_shared_prompts():
    """Получить список общих (shared) промптов.
    
    Доступно всем (без авторизации).
    
    Returns:
        JSON: {"success": true, "prompts": [...]}
    """
    db = next(get_db())
    try:
        service = PromptService(db)
        prompts = service.get_shared_prompts()
        
        return jsonify({
            'success': True,
            'prompts': prompts
        })
    finally:
        db.close()
