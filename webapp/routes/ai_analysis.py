"""Blueprint для модуля AI анализа через GPT."""
import os
from flask import Blueprint, request, jsonify, current_app
from webapp.services.gpt_analysis import GPTAnalysisService, PromptManager
from webapp.services.state import FilesState
from document_processor.core import DocumentProcessor


ai_analysis_bp = Blueprint('ai_analysis', __name__, url_prefix='/ai_analysis')


def _get_files_state():
    """Получить экземпляр FilesState."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@ai_analysis_bp.route('/analyze', methods=['POST'])
def analyze():
    """
    Выполнить AI анализ выбранных файлов.
    
    Ожидает JSON:
    {
        "file_paths": ["path1", "path2", ...],
        "prompt": "текст промпта",
        "max_request_size": 4096
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
        max_request_size = data.get('max_request_size', 4096)
        
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
        
        current_app.logger.info(f'AI анализ: получено {len(file_paths)} файлов')
        
        # Собираем текст из выбранных файлов
        upload_folder = current_app.config['UPLOAD_FOLDER']
        combined_text = _extract_text_from_files(file_paths, upload_folder)
        
        if not combined_text:
            return jsonify({
                'success': False,
                'message': 'Не удалось извлечь текст из файлов'
            }), 400
        
        current_app.logger.info(f'Извлечено {len(combined_text)} символов текста')
        
        # Проверяем размер до отправки
        full_request = f"{prompt}\n\n{combined_text}"
        if len(full_request) > max_request_size:
            return jsonify({
                'success': False,
                'message': 'Размер запроса превышает лимит',
                'current_size': len(full_request),
                'max_size': max_request_size,
                'excess': len(full_request) - max_request_size,
                'text': combined_text  # Возвращаем текст для ручного редактирования
            }), 400
        
        # Отправляем на анализ
        gpt_service = GPTAnalysisService()
        success, message, gpt_response = gpt_service.analyze_text(
            combined_text,
            prompt,
            max_request_size
        )
        
        if success:
            current_app.logger.info('AI анализ выполнен успешно')
            return jsonify({
                'success': True,
                'message': message,
                'response': gpt_response,
                'request_size': len(full_request)
            }), 200
        else:
            current_app.logger.error(f'Ошибка AI анализа: {message}')
            return jsonify({
                'success': False,
                'message': message
            }), 500
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/analyze: {e}')
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500


@ai_analysis_bp.route('/optimize_text', methods=['POST'])
def optimize_text():
    """
    Оптимизировать текст для уменьшения размера.
    
    Ожидает JSON:
    {
        "text": "исходный текст",
        "target_size": 3000
    }
    
    Returns:
        JSON с оптимизированным текстом
    """
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({
                'success': False,
                'message': 'Не передан текст'
            }), 400
        
        text = data['text']
        target_size = data.get('target_size', 3000)
        
        gpt_service = GPTAnalysisService()
        optimized_text = gpt_service.optimize_text(text, target_size)
        
        return jsonify({
            'success': True,
            'optimized_text': optimized_text,
            'original_size': len(text),
            'optimized_size': len(optimized_text),
            'reduction': len(text) - len(optimized_text)
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/optimize_text: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка оптимизации: {str(e)}'
        }), 500


@ai_analysis_bp.route('/prompts/save', methods=['POST'])
def save_prompt():
    """
    Сохранить промпт.
    
    Ожидает JSON:
    {
        "prompt": "текст промпта",
        "filename": "имя файла (опционально)"
    }
    
    Returns:
        JSON с результатом сохранения
    """
    try:
        data = request.get_json()
        
        if not data or 'prompt' not in data:
            return jsonify({
                'success': False,
                'message': 'Не передан промпт'
            }), 400
        
        prompt = data['prompt']
        filename = data.get('filename')
        
        prompts_folder = current_app.config.get('PROMPTS_FOLDER', 'PROMPT')
        manager = PromptManager(prompts_folder)
        
        success, message = manager.save_prompt(prompt, filename)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 500
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/prompts/save: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка сохранения промпта: {str(e)}'
        }), 500


@ai_analysis_bp.route('/prompts/load/<filename>', methods=['GET'])
def load_prompt(filename):
    """
    Загрузить промпт из файла.
    
    Returns:
        JSON с текстом промпта
    """
    try:
        prompts_folder = current_app.config.get('PROMPTS_FOLDER', 'PROMPT')
        manager = PromptManager(prompts_folder)
        
        success, message, prompt = manager.load_prompt(filename)
        
        if success:
            return jsonify({
                'success': True,
                'prompt': prompt
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 404
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/prompts/load: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка загрузки промпта: {str(e)}'
        }), 500


@ai_analysis_bp.route('/prompts/last', methods=['GET'])
def get_last_prompt():
    """
    Получить последний использованный промпт.
    
    Returns:
        JSON с текстом промпта
    """
    try:
        prompts_folder = current_app.config.get('PROMPTS_FOLDER', 'PROMPT')
        manager = PromptManager(prompts_folder)
        
        prompt = manager.get_last_prompt()
        
        return jsonify({
            'success': True,
            'prompt': prompt
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/prompts/last: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка получения промпта: {str(e)}'
        }), 500


@ai_analysis_bp.route('/prompts/list', methods=['GET'])
def list_prompts():
    """
    Получить список сохранённых промптов.
    
    Returns:
        JSON со списком файлов
    """
    try:
        prompts_folder = current_app.config.get('PROMPTS_FOLDER', 'PROMPT')
        manager = PromptManager(prompts_folder)
        
        prompts = manager.list_prompts()
        
        return jsonify({
            'success': True,
            'prompts': prompts
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/prompts/list: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка получения списка промптов: {str(e)}'
        }), 500


def _extract_text_from_files(file_paths, upload_folder):
    """
    Извлечь текст из указанных файлов.
    
    Args:
        file_paths: Список относительных путей к файлам
        upload_folder: Базовая папка с файлами
        
    Returns:
        Объединённый текст из всех файлов
    """
    processor = DocumentProcessor()
    combined_text = []
    
    for rel_path in file_paths:
        try:
            # Формируем полный путь
            full_path = os.path.join(upload_folder, rel_path)
            
            if not os.path.exists(full_path):
                current_app.logger.warning(f'Файл не найден: {full_path}')
                continue
            
            # Извлекаем текст
            text = processor.extract_text(full_path)
            
            if text:
                # Добавляем заголовок файла
                combined_text.append(f"=== {os.path.basename(rel_path)} ===")
                combined_text.append(text)
                combined_text.append("")  # Пустая строка между файлами
            
        except Exception as e:
            current_app.logger.error(f'Ошибка извлечения текста из {rel_path}: {e}')
    
    return '\n'.join(combined_text)
