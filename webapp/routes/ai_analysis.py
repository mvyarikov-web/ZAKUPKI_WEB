"""Blueprint для модуля AI анализа через GPT."""
import os
from flask import Blueprint, request, jsonify, current_app, render_template
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
        override_text = data.get('override_text', None)
        
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

        # Если передан override_text (из окна оптимизации) — используем его
        if isinstance(override_text, str) and override_text.strip():
            combined_text = override_text
        else:
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


@ai_analysis_bp.route('/get_texts', methods=['POST'])
def get_texts():
    """Вернуть тексты выбранных файлов (по индексу) для редактора оптимизации."""
    try:
        data = request.get_json() or {}
        file_paths = data.get('file_paths', [])
        if not file_paths:
            return jsonify({'success': False, 'message': 'Не выбраны файлы'}), 400

        index_folder = current_app.config.get('INDEX_FOLDER')
        index_path = get_index_path(index_folder) if index_folder else None
        if not index_path or not os.path.exists(index_path):
            return jsonify({'success': False, 'message': 'Сводный индекс не найден'}), 400

        # Извлечём тексты по каждому пути отдельно
        docs = []
        try:
            with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return jsonify({'success': False, 'message': 'Не удалось прочитать индекс'}), 500

        for rel_path in file_paths:
            text = _extract_single_from_index(content, rel_path)
            docs.append({'path': rel_path, 'text': text or '', 'length': len(text or '')})

        return jsonify({'success': True, 'docs': docs}), 200
    except Exception as e:
        current_app.logger.exception('Ошибка в /ai_analysis/get_texts: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_analysis_bp.route('/workspace/save', methods=['POST'])
def save_workspace():
    """Сохранить рабочее состояние оптимизации в файл (JSON и TXT)."""
    try:
        data = request.get_json() or {}
        prompt = data.get('prompt', '')
        docs = data.get('docs', [])  # [{'path','text'}]
        if not isinstance(docs, list):
            return jsonify({'success': False, 'message': 'Некорректный формат docs'}), 400

        index_folder = current_app.config.get('INDEX_FOLDER')
        if not index_folder:
            return jsonify({'success': False, 'message': 'INDEX_FOLDER не настроен'}), 500
        os.makedirs(index_folder, exist_ok=True)

        json_path = os.path.join(index_folder, 'ai_workspace.json')
        txt_path = os.path.join(index_folder, 'ai_workspace.txt')

        # Сохраняем JSON
        payload = {'prompt': prompt, 'docs': docs}
        try:
            import json
            with open(json_path, 'w', encoding='utf-8') as jf:
                json.dump(payload, jf, ensure_ascii=False, indent=2)
        except Exception as e:
            current_app.logger.exception('Ошибка сохранения JSON воркспейса: %s', e)
            return jsonify({'success': False, 'message': 'Не удалось сохранить JSON воркспейс'}), 500

        # Сохраняем TXT для ручного просмотра/редактирования
        try:
            with open(txt_path, 'w', encoding='utf-8') as tf:
                tf.write(f"PROMPT:\n{prompt}\n\n")
                for d in docs:
                    tf.write(f"===== {d.get('path','(без имени)')} =====\n")
                    tf.write((d.get('text') or '') + "\n\n")
        except Exception as e:
            current_app.logger.exception('Ошибка сохранения TXT воркспейса: %s', e)
            # Не критично: продолжаем

        return jsonify({'success': True, 'message': 'Воркспейс сохранён', 'json_path': json_path, 'txt_path': txt_path}), 200
    except Exception as e:
        current_app.logger.exception('Ошибка в /ai_analysis/workspace/save: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_analysis_bp.route('/workspace', methods=['GET'])
def get_workspace():
    """Получить сохранённый воркспейс (если есть)."""
    try:
        index_folder = current_app.config.get('INDEX_FOLDER')
        json_path = os.path.join(index_folder, 'ai_workspace.json') if index_folder else None
        if not json_path or not os.path.exists(json_path):
            return jsonify({'success': True, 'exists': False, 'prompt': '', 'docs': []}), 200
        import json
        with open(json_path, 'r', encoding='utf-8') as jf:
            payload = json.load(jf)
        return jsonify({'success': True, 'exists': True, 'prompt': payload.get('prompt',''), 'docs': payload.get('docs', [])}), 200
    except Exception as e:
        current_app.logger.exception('Ошибка в /ai_analysis/workspace: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 500


def _extract_single_from_index(index_content: str, rel_path: str) -> str:
    """Извлечь текст одного документа из содержимого индекса по rel_path."""
    try:
        DOC_START_MARKER = "<<< НАЧАЛО ДОКУМЕНТА >>>"
        DOC_END_MARKER = "<<< КОНЕЦ ДОКУМЕНТА >>>"
        # Ищем заголовок соответствующего файла
        marker = f"ЗАГОЛОВОК: {rel_path}\n"
        start_pos = index_content.find(marker)
        if start_pos == -1:
            return ''
        # От начала заголовка ищем маркер начала документа
        doc_start = index_content.find(DOC_START_MARKER, start_pos)
        if doc_start == -1:
            return ''
        doc_start += len(DOC_START_MARKER) + 1  # +\n
        # Ищем конец документа
        doc_end = index_content.find(DOC_END_MARKER, doc_start)
        if doc_end == -1:
            return ''
        body = index_content[doc_start:doc_end]
        return body.strip()
    except Exception:
        return ''


@ai_analysis_bp.route('/test_models', methods=['GET'])
def test_models():
    """Страница для тестирования моделей."""
    return render_template('test_models.html')


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


@ai_analysis_bp.route('/optimize/preview', methods=['POST'])
def optimize_preview():
    """
    Предпросмотр оптимизации текста.
    
    Ожидает JSON:
    {
        "text": "<исходный_текст>"
    }
    
    Returns:
        JSON с оптимизированным текстом и метриками
    """
    try:
        from webapp.services.text_optimizer import get_text_optimizer
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Не переданы данные'
            }), 400
        
        text = data.get('text', '')
        
        if not text or not text.strip():
            return jsonify({
                'success': False,
                'message': 'Нет текста для оптимизации'
            }), 400
        
        # Проверка размера текста (max 1MB)
        if len(text) > 1_000_000:
            return jsonify({
                'success': False,
                'message': 'Текст слишком большой для оптимизации (максимум 1MB)'
            }), 400
        
        # Выполняем оптимизацию
        optimizer = get_text_optimizer()
        result = optimizer.optimize(text)
        
        # Формируем ответ (всегда success=True, показываем модалку)
        response_data = {
            'success': True,
            'optimized_text': result.optimized_text,
            'change_spans': [
                {
                    'start': span.start,
                    'end': span.end,
                    'reason': span.reason
                }
                for span in result.change_spans
            ],
            'chars_before': result.chars_before,
            'chars_after': result.chars_after,
            'reduction_pct': result.reduction_pct
        }
        
        # Если изменений нет или они минимальны, добавляем информационное сообщение
        if result.reduction_pct < 1.0:
            response_data['info_message'] = 'Текст уже оптимален, изменения не требуются'
        
        return jsonify(response_data), 200
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка оптимизации текста: {e}')
        return jsonify({
            'success': False,
            'message': f'Ошибка оптимизации: {str(e)}'
        }), 500
