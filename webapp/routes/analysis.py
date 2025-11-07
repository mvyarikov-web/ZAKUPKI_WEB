"""Blueprint для модуля анализа текста (DB-first).

Примечание: анализ по файловому индексу (_search_index.txt) отключён в DB-first.
"""
import os
from flask import Blueprint, request, jsonify, current_app, send_file
from webapp.services.analysis import save_analysis


analysis_bp = Blueprint('analysis', __name__, url_prefix='/analysis')


@analysis_bp.route('/run', methods=['POST'])
def run_analysis_endpoint():
    """Запуск анализа.

    В DB-first режиме файловый анализ _search_index.txt недоступен.
    """
    try:
        if current_app.config.get('use_database', False):
            return jsonify({
                'success': False,
                'message': 'Анализ по файловому индексу отключён (DB-first).'
            }), 400
        # Legacy-фолбэк не реализуем в DB-first ветке
        return jsonify({'success': False, 'message': 'Функция недоступна в текущей конфигурации'}), 400
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /analysis/run: {e}')
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500


@analysis_bp.route('/save', methods=['POST'])
def save_analysis_endpoint():
    """
    Сохраняет результаты анализа (возможно отредактированные пользователем).
    
    Expects JSON with 'data' field containing the analysis results.
    
    Returns:
        JSON с URL отчёта или ошибкой
    """
    try:
        data = request.get_json()
        
        if not data or 'data' not in data:
            return jsonify({
                'success': False,
                'message': 'Не переданы данные для сохранения'
            }), 400
        
        result_data = data['data']
        index_folder = current_app.config['INDEX_FOLDER']
        
        # Сохраняем результаты
        success, message, report_url = save_analysis(result_data, index_folder)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'report_url': report_url
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 500
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /analysis/save: {e}')
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500


@analysis_bp.route('/report/', methods=['GET'])
def get_report():
    """
    Отдаёт HTML-отчёт для открытия в новой вкладке.
    
    Returns:
        HTML-файл отчёта
    """
    try:
        index_folder = current_app.config['INDEX_FOLDER']
        report_path = os.path.join(index_folder, 'analysis_report.html')
        
        if not os.path.exists(report_path):
            return 'Отчёт не найден. Сначала выполните анализ и сохраните результаты.', 404
        
        return send_file(
            report_path,
            mimetype='text/html',
            as_attachment=False,
            download_name='analysis_report.html'
        )
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка при отдаче отчёта: {e}')
        return f'Ошибка при загрузке отчёта: {str(e)}', 500


@analysis_bp.route('/status', methods=['GET'])
def get_analysis_status():
    """
    Проверяет статус модуля анализа и наличие результатов.
    
    Returns:
        JSON со статусом
    """
    try:
        index_folder = current_app.config['INDEX_FOLDER']
        json_path = os.path.join(index_folder, 'analysis_result.json')
        report_path = os.path.join(index_folder, 'analysis_report.html')
        
        return jsonify({
            'mode': 'db-first' if current_app.config.get('use_database', False) else 'legacy',
            'index_exists': False,  # файловый индекс не используется в DB-first
            'analysis_exists': os.path.exists(json_path),
            'report_exists': os.path.exists(report_path)
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /analysis/status: {e}')
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
