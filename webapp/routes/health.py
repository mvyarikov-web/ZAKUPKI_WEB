"""Blueprint для health check эндпоинта."""
import os
import json
from flask import Blueprint, jsonify, current_app

health_bp = Blueprint('health', __name__)


@health_bp.get('/health')
def health_check():
    """Проверка работоспособности приложения."""
    return jsonify({'status': 'ok'}), 200
