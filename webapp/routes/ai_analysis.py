"""Blueprint для модуля AI анализа через GPT."""
import os
from flask import Blueprint, request, jsonify, current_app
from webapp.services.gpt_analysis import GPTAnalysisService, PromptManager
from webapp.services.indexing import get_index_path
from webapp.services.state import FilesState
from document_processor.core import DocumentProcessor


ai_analysis_bp = Blueprint('ai_analysis', __name__, url_prefix='/ai_analysis')


def _get_files_state():
    """Получить экземпляр FilesState."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@ai_analysis_bp.route('/get_text_size', methods=['POST'])
def get_text_size():
    """
    Получить размер текста для выбранных файлов без выполнения анализа.
    
    Ожидает JSON:
    {
        "file_paths": ["path1", "path2", ...],
        "prompt": "текст промпта"
    }
    
    Returns:
        JSON с информацией о размерах
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
        
        if not file_paths:
            return jsonify({
                'success': False,
                'message': 'Не выбраны файлы для анализа'
            }), 400
        
        # Собираем текст из индекса
        index_folder = current_app.config.get('INDEX_FOLDER')
        index_path = get_index_path(index_folder) if index_folder else None

        if not index_path or not os.path.exists(index_path):
            return jsonify({
                'success': False,
                'message': 'Сводный индекс не найден. Постройте индекс через кнопку «Построить индекс».'
            }), 400

        combined_text = _extract_text_from_index_for_files(file_paths, index_path)

        if not combined_text:
            upload_folder = current_app.config['UPLOAD_FOLDER']
            combined_text = _extract_text_from_files(file_paths, upload_folder)
        
        if not combined_text:
            return jsonify({
                'success': False,
                'message': 'Не удалось извлечь текст из файлов'
            }), 400
        
        # Считаем размеры
        text_size = len(combined_text)
        prompt_size = len(prompt)
        total_size = text_size + prompt_size + 2  # +2 для переноса строк
        max_size = current_app.config.get('GPT_MAX_REQUEST_SIZE', 4096)
        
        return jsonify({
            'success': True,
            'text_size': text_size,
            'prompt_size': prompt_size,
            'total_size': total_size,
            'max_size': max_size,
            'exceeds_limit': total_size > max_size,
            'excess': max(0, total_size - max_size)
        }), 200
            
    except Exception as e:
        current_app.logger.exception(f'Ошибка в /ai_analysis/get_text_size: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка получения размера: {str(e)}'
        }), 500


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
        
        # Собираем текст из индекса (FR-003: источник данных — только индекс)
        index_folder = current_app.config.get('INDEX_FOLDER')
        index_path = get_index_path(index_folder) if index_folder else None

        if not index_path or not os.path.exists(index_path):
            return jsonify({
                'success': False,
                'message': 'Сводный индекс не найден. Постройте индекс через кнопку «Построить индекс».'
            }), 400

        combined_text = _extract_text_from_index_for_files(file_paths, index_path)

        # Безопасный фолбэк: если по какой-то причине текста нет в индексе (не должен происходить при валидном индексе),
        # пробуем старый способ извлечения из исходных файлов. Это не блокирует UI и сработает только точечно.
        if not combined_text:
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


def _extract_text_from_index_for_files(file_paths, index_path: str) -> str:
    """Извлекает текст для набора файлов из сводного индекса.

    Использует маркеры начала/конца документа, чтобы получить тело, и не обращается к исходным файлам.
    Совместимо с виртуальными путями из архивов (zip://, rar://). Возвращает объединённый текст
    c простыми разделителями между файлами.

    Args:
        file_paths: Список относительных путей к файлам (как в UI/индексе)
        index_path: Полный путь к '_search_index.txt'

    Returns:
        Строка объединённого текста
    """
    DOC_START_MARKER = "<<< НАЧАЛО ДОКУМЕНТА >>>"
    DOC_END_MARKER = "<<< КОНЕЦ ДОКУМЕНТА >>>"

    try:
        import re
        # Читаем индекс один раз для эффективности
        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        chunks: list[str] = []

        for rel_path in file_paths:
            try:
                # Нормализуем для поиска по индексу
                norm = (rel_path or '').replace('\\', '/')
                norm_clean = re.sub(r'^(zip://|rar://)', '', norm)

                # Пытаемся найти соответствующий заголовок
                patterns = [
                    rf"ЗАГОЛОВОК: {re.escape(norm)}\n",
                    rf"ЗАГОЛОВОК: {re.escape(norm_clean)}\n",
                    rf"ЗАГОЛОВОК: .*{re.escape(os.path.basename(norm))}\n",
                    rf"ЗАГОЛОВОК: .*{re.escape(os.path.basename(norm_clean))}\n",
                ]

                extracted = ''
                for pat in patterns:
                    for m in re.finditer(pat, content, re.MULTILINE | re.IGNORECASE):
                        start_pos = content.find(DOC_START_MARKER, m.end())
                        if start_pos == -1:
                            continue
                        end_pos = content.find(DOC_END_MARKER, start_pos + len(DOC_START_MARKER))
                        if end_pos == -1:
                            body = content[start_pos + len(DOC_START_MARKER):].strip()
                        else:
                            body = content[start_pos + len(DOC_START_MARKER):end_pos].strip()
                        if body:
                            extracted = body
                            break
                    if extracted:
                        break

                if extracted:
                    chunks.append(f"=== {os.path.basename(rel_path)} ===\n{extracted}\n")
                else:
                    current_app.logger.debug("Текст в индексе не найден для: %s", rel_path)
            except Exception:
                current_app.logger.debug("Ошибка извлечения из индекса для: %s", rel_path, exc_info=True)

        return '\n'.join(chunks).strip()
    except Exception:
        current_app.logger.exception('Сбой извлечения текста из индекса для AI-анализа')
        return ''
