"""Blueprint для модуля AI анализа через GPT."""
import os
from typing import Dict, List, Tuple

from flask import Blueprint, request, jsonify, current_app, render_template, g

from webapp.config.config_service import get_config
from webapp.models.rag_models import RAGDatabase
from webapp.services.gpt_analysis import GPTAnalysisService, PromptManager
from webapp.services.file_search_state_service import FileSearchStateService


ai_analysis_bp = Blueprint('ai_analysis', __name__, url_prefix='/ai_analysis')


def _get_files_state():
    """Получить экземпляр FileSearchStateService."""
    # Сервис сам определит путь к файлу из конфига
    return FileSearchStateService()


def _get_db() -> RAGDatabase:
    """Получить объект работы с БД (кешируется в контексте запроса)."""
    if 'db' not in g:
        config = get_config()
        dsn = config.database_url
        if dsn.startswith('postgresql+psycopg2://'):
            dsn = dsn.replace('postgresql+psycopg2://', 'postgresql://', 1)
        g.db = RAGDatabase(dsn)
    return g.db


def _required_user_id() -> int:
    """Строго получить идентификатор пользователя с учётом STRICT_USER_ID."""
    config = get_config()
    strict = config.strict_user_id

    # g.user.id
    user = getattr(g, 'user', None)
    if user and getattr(user, 'id', None):
        return int(user.id)

    # Заголовок X-User-ID
    header_id = request.headers.get('X-User-ID')
    if header_id and str(header_id).isdigit():
        return int(header_id)

    if strict:
        raise ValueError('user_id отсутствует (STRICT_USER_ID)')
    return 1


def _sanitize_paths(file_paths: List[str]) -> Tuple[List[str], List[str], Dict[str, str]]:
    """Проверить и нормализовать пути, сохранив исходные значения.

    Returns:
        tuple: (валидные, отклонённые, отображение нормализованных путей к исходным)
    """
    valid: List[str] = []
    rejected: List[str] = []
    mapping: Dict[str, str] = {}

    for raw in file_paths:
        if not isinstance(raw, str):
            rejected.append(str(raw))
            continue
        candidate = raw.strip()
        if not candidate:
            rejected.append(raw)
            continue
        norm = os.path.normpath(candidate).replace('\\', '/')
        if norm.startswith('../') or norm.startswith('..\\') or norm == '..':
            rejected.append(raw)
            continue
        if os.path.isabs(norm):
            rejected.append(raw)
            continue
        if any(part == '..' for part in norm.split('/') if part):
            rejected.append(raw)
            continue
        if norm == '.':
            rejected.append(raw)
            continue
        mapping[norm] = raw
        if norm not in valid:
            valid.append(norm)

    return valid, rejected, mapping


def _fetch_documents_from_db(db: RAGDatabase, owner_id: int, file_paths: List[str]) -> Tuple[str, List[Dict[str, str]], List[str]]:
    """Получить тексты документов из БД по user_path."""
    if not file_paths:
        return '', [], []

    valid, rejected, mapping = _sanitize_paths(file_paths)
    if not valid:
        return '', [], rejected

    docs: List[Dict[str, str]] = []
    missing: List[str] = rejected.copy()
    combined_parts: List[str] = []

    try:
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ud.user_path, d.id, COALESCE(ud.original_filename, d.sha256) AS display_name
                    FROM user_documents ud
                    JOIN documents d ON d.id = ud.document_id
                    WHERE ud.user_id = %s
                      AND ud.is_soft_deleted = FALSE
                      AND ud.user_path = ANY(%s);
                    """,
                    (owner_id, valid)
                )
                rows = cur.fetchall()

                path_to_doc: Dict[str, Tuple[int, str]] = {
                    row[0]: (int(row[1]), row[2]) for row in rows
                }

                if not path_to_doc:
                    return '', [], [mapping.get(v, v) for v in valid]

                doc_ids = [doc_id for doc_id, _ in path_to_doc.values()]
                chunk_rows = []
                if doc_ids:
                    cur.execute(
                        """
                        SELECT c.document_id, c.chunk_idx, c.text
                        FROM chunks c
                        WHERE c.document_id = ANY(%s)
                        ORDER BY c.document_id, c.chunk_idx;
                        """,
                        (doc_ids,)
                    )
                    chunk_rows = cur.fetchall()

        chunks_by_doc: Dict[int, List[str]] = {}
        for doc_id, _, text in chunk_rows:
            chunks_by_doc.setdefault(int(doc_id), []).append(text or '')

        for norm_path in valid:
            if norm_path not in path_to_doc:
                missing.append(mapping.get(norm_path, norm_path))
                continue
            doc_id, display_name = path_to_doc[norm_path]
            chunk_list = chunks_by_doc.get(doc_id, [])
            text = '\n\n'.join(chunk_list).strip()
            original = mapping.get(norm_path, norm_path)
            docs.append({
                'path': original,
                'display_name': display_name,
                'text': text,
                'length': len(text)
            })
            if text:
                combined_parts.append(f"=== {display_name or os.path.basename(original)} ===")
                combined_parts.append(text)
                combined_parts.append('')

    except Exception:
        current_app.logger.exception('Не удалось получить тексты документов из БД')
        raise

    combined_text = '\n'.join(combined_parts).strip()
    return combined_text, docs, missing


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
        
        if not current_app.config.get('use_database', False):
            return jsonify({
                'success': False,
                'message': 'Режим БД отключён, AI анализ недоступен'
            }), 400

        try:
            db = _get_db()
            owner_id = _required_user_id()
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Не указан идентификатор пользователя (X-User-ID)'
            }), 400

        combined_text, _, missing = _fetch_documents_from_db(db, owner_id, file_paths)

        if missing:
            current_app.logger.warning('AI анализ: отсутствуют файлы %s', missing)
            return jsonify({
                'success': False,
                'message': f"Файлы не найдены в индексе: {', '.join(missing)}"
            }), 404
        
        if not combined_text:
            return jsonify({
                'success': False,
                'message': 'Не удалось получить текст документов'
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

        if not current_app.config.get('use_database', False):
            return jsonify({
                'success': False,
                'message': 'Режим БД отключён, AI анализ недоступен'
            }), 400

        try:
            db = _get_db()
            owner_id = _required_user_id()
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Не указан идентификатор пользователя (X-User-ID)'
            }), 400

        override_text_clean = override_text.strip() if isinstance(override_text, str) else ''
        combined_text = ''

        if override_text_clean:
            # Проверяем доступность файлов, но используем предоставленный текст
            _, _, missing = _fetch_documents_from_db(db, owner_id, file_paths)
            if missing:
                current_app.logger.warning('AI анализ: отсутствуют файлы %s', missing)
                return jsonify({
                    'success': False,
                    'message': f"Файлы не найдены в индексе: {', '.join(missing)}"
                }), 404
            combined_text = override_text_clean
        else:
            combined_text, _, missing = _fetch_documents_from_db(db, owner_id, file_paths)
            if missing:
                current_app.logger.warning('AI анализ: отсутствуют файлы %s', missing)
                return jsonify({
                    'success': False,
                    'message': f"Файлы не найдены в индексе: {', '.join(missing)}"
                }), 404
        
        if not combined_text:
            return jsonify({
                'success': False,
                'message': 'Не удалось получить текст документов'
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

        if not current_app.config.get('use_database', False):
            return jsonify({'success': False, 'message': 'Режим БД отключён, тексты недоступны'}), 400

        try:
            db = _get_db()
            owner_id = _required_user_id()
        except ValueError:
            return jsonify({'success': False, 'message': 'Не указан идентификатор пользователя (X-User-ID)'}), 400

        _, docs, missing = _fetch_documents_from_db(db, owner_id, file_paths)
        if missing:
            return jsonify({'success': False, 'message': f"Файлы не найдены в индексе: {', '.join(missing)}"}), 404

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
        
        # TODO: добавить @require_auth и использовать g.user.id
        # Пока используем admin (user_id=5) для обратной совместимости
        from flask import g
        user_id = getattr(g, 'user', None)
        if user_id:
            user_id = user_id.id
        else:
            user_id = 5  # fallback на admin
        
        manager = PromptManager(user_id)
        
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
        # TODO: добавить @require_auth и использовать g.user.id
        from flask import g
        user_id = getattr(g, 'user', None)
        if user_id:
            user_id = user_id.id
        else:
            user_id = 5  # fallback на admin
        
        manager = PromptManager(user_id)
        
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
        # TODO: добавить @require_auth и использовать g.user.id
        from flask import g
        user_id = getattr(g, 'user', None)
        if user_id:
            user_id = user_id.id
        else:
            user_id = 5  # fallback на admin
        
        manager = PromptManager(user_id)
        
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
        JSON со списком промптов
    """
    try:
        # TODO: добавить @require_auth и использовать g.user.id
        from flask import g
        user_id = getattr(g, 'user', None)
        if user_id:
            user_id = user_id.id
        else:
            user_id = 5  # fallback на admin
        
        manager = PromptManager(user_id)
        
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
