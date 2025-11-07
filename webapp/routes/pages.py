"""Blueprint для страниц (index, view)."""
import os
from urllib.parse import unquote
from flask import Blueprint, render_template, jsonify, request, current_app, send_from_directory, g
from markupsafe import Markup
from webapp.services.files import allowed_file, is_safe_subpath
from webapp.services.state import FilesState
from webapp.middleware.auth_middleware import require_auth

pages_bp = Blueprint('pages', __name__)


def _get_files_state():
    """Получить экземпляр FilesState для текущего приложения."""
    results_file = current_app.config['SEARCH_RESULTS_FILE']
    return FilesState(results_file)


@pages_bp.route('/')
def index():
    """Главная страница"""
    # Загружаем сохраненные результаты поиска
    files_state = _get_files_state()
    last_search_terms = files_state.get_last_search_terms()
    file_status = files_state.get_file_status()
    
    # Получаем список загруженных файлов с группировкой по папкам
    files_by_folder = {}
    total_files = 0
    
    current_app.logger.info(f"Проверяем папку: {current_app.config['UPLOAD_FOLDER']}")
    
    if os.path.exists(current_app.config['UPLOAD_FOLDER']):
        # Рекурсивно обходим все файлы и папки
        for root, dirs, files in os.walk(current_app.config['UPLOAD_FOLDER']):
            for filename in files:
                # Скрываем служебный индексный файл и временные файлы Office
                if filename == '_search_index.txt' or filename.startswith('~$') or filename.startswith('$'):
                    continue
                file_path = os.path.join(root, filename)
                # Определяем относительную папку
                relative_folder = os.path.relpath(root, current_app.config['UPLOAD_FOLDER'])

                # Правильно определяем название папки
                if relative_folder == '.':
                    folder_display_name = '📁 Загруженные файлы'
                    folder_key = 'root'
                else:
                    folder_parts = relative_folder.split(os.sep)
                    original_folder_name = folder_parts[-1]
                    folder_display_name = f'📂 {original_folder_name}'
                    folder_key = relative_folder

                file_size = os.path.getsize(file_path)
                file_key = os.path.join(relative_folder, filename) if relative_folder != '.' else filename
                file_data = file_status.get(file_key, {})
                status = file_data.get('status', 'not_checked')
                # Если формат не поддерживается — пометим явно
                if not allowed_file(filename, current_app.config['ALLOWED_EXTENSIONS']):
                    status = 'unsupported'
                    file_data = {**file_data, 'status': 'unsupported', 'error': 'Неподдерживаемый формат'}
                    files_state.set_file_status(file_key, 'unsupported', 
                                               {'error': 'Неподдерживаемый формат'})

                display_name = file_data.get('original_name', filename)
                file_info = {
                    'name': display_name,
                    'size': file_size,
                    'status': status,
                    'path': file_key,
                    'relative_folder': relative_folder
                }

                if folder_key not in files_by_folder:
                    files_by_folder[folder_key] = {
                        'display_name': folder_display_name,
                        'relative_path': relative_folder,
                        'files': []
                    }

                files_by_folder[folder_key]['files'].append(file_info)
                total_files += 1
                current_app.logger.debug(f"Добавлен файл: {filename} в папку {folder_display_name}, размер: {file_size}, статус: {status}")
    else:
        current_app.logger.warning("Папка uploads не существует")
    
    current_app.logger.info(f"Всего файлов для отображения: {total_files}, папок: {len(files_by_folder)}")
    
    # Выбираем правильный шаблон в зависимости от режима БД
    template_name = 'index_with_auth.html' if current_app.config.get('use_database') else 'index.html'
    
    return render_template(
        template_name,
        files_by_folder=files_by_folder,
        total_files=total_files,
        last_search_terms=last_search_terms,
        file_status=file_status,
    )


@pages_bp.route('/view/<path:filepath>')
def view_file(filepath):
    """Просмотр содержимого файла из индекса (DB-first через RAGDatabase, increment-015)."""
    from flask import g
    from webapp.models.rag_models import RAGDatabase
    from webapp.config import get_config
    
    def _get_db() -> RAGDatabase:
        """Получить подключение к БД (кешируется в g)."""
        if 'db' not in g:
            config = get_config()
            dsn = config.database_url.replace('postgresql+psycopg2://', 'postgresql://')
            g.db = RAGDatabase(dsn)
        return g.db
    
    def required_user_id() -> int:
        from webapp.config.config_service import get_config as _gc
        config = _gc()
        strict = config.strict_user_id
        # 1) middleware
        try:
            user = getattr(g, 'user', None)
            if user and getattr(user, 'id', None):
                return int(user.id)
        except Exception:
            pass
        # 2) header
        try:
            uid = request.headers.get('X-User-ID')
            if uid and str(uid).isdigit():
                return int(uid)
        except Exception:
            pass
        if strict:
            raise ValueError('user_id отсутствует (STRICT_USER_ID)')
        return 1

    try:
        decoded_filepath = unquote(filepath)
        current_app.logger.info(f"Просмотр файла: {decoded_filepath}")
        
        # Проверка безопасности пути
        if not is_safe_subpath(current_app.config['UPLOAD_FOLDER'], decoded_filepath):
            return jsonify({'error': 'Недопустимый путь к файлу'}), 400
        
        # Получаем документ и чанки из БД через RAGDatabase
        db = _get_db()
        try:
            owner_id = required_user_id()
        except ValueError:
            return jsonify({'error': 'Не указан идентификатор пользователя (X-User-ID)'}), 400
        
        document = None
        chunks = []
        
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                # Ищем документ по user_path через связь user_documents
                cur.execute(
                    """
                    SELECT d.id, COALESCE(ud.original_filename, d.sha256) AS filename, 'indexed' AS status
                    FROM user_documents ud
                    JOIN documents d ON d.id = ud.document_id
                    WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE AND ud.user_path = %s
                    LIMIT 1;
                    """,
                    (owner_id, decoded_filepath)
                )
                doc_row = cur.fetchone()
                if not doc_row:
                    current_app.logger.warning(f"Документ не найден в БД: {decoded_filepath}")
                    return jsonify({'error': 'Документ не найден в индексе.'}), 404
                doc_id, filename, status = doc_row
                document = {'id': doc_id, 'filename': filename, 'status': status}
                # Получаем чанки документа
                cur.execute(
                    """
                    SELECT text
                    FROM chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index;
                    """,
                    (doc_id,)
                )
                chunks = [r[0] for r in cur.fetchall()]
        
        if not chunks:
            current_app.logger.warning(f"Чанки не найдены для документа: {decoded_filepath}")
            return render_template(
                'view.html',
                title=os.path.basename(decoded_filepath),
                content=Markup('<div class="error-message">Не удалось извлечь текст документа</div>'),
                keywords=[]
            )
        
        # Собираем текст из чанков
        text = '\n\n'.join(chunks)
        
        # Получаем ключевые слова из query параметра
        query = request.args.get('q', '')
        keywords = [k.strip() for k in query.split(',') if k.strip()] if query else []
        
        # Подсветка ключевых слов
        if keywords:
            import re
            for keyword in keywords:
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                text = pattern.sub(lambda m: f'<mark>{m.group(0)}</mark>', text)
        
        # Экранируем HTML для безопасности (кроме наших mark)
        # text уже содержит <mark>, поэтому используем Markup
        safe_text = Markup(text.replace('<', '&lt;').replace('>', '&gt;')
                          .replace('&lt;mark&gt;', '<mark>')
                          .replace('&lt;/mark&gt;', '</mark>'))
        
        return render_template(
            'view.html',
            title=os.path.basename(decoded_filepath),
            content=safe_text,
            keywords=keywords
        )
    
    except Exception as e:
        current_app.logger.exception('view_file error')
        return jsonify({'error': str(e)}), 500


@pages_bp.route('/test_models')
def test_models():
    """Тестовая страница для проверки загрузки моделей."""
    return render_template('test_models.html')


@pages_bp.route('/test_messages')
def test_messages():
    """Тестовая страница для проверки системы сообщений MessageManager."""
    # Отдаём HTML файл напрямую из корневой директории проекта
    from pathlib import Path
    project_root = Path(current_app.root_path).parent
    test_file = project_root / 'test_messages.html'
    
    if test_file.exists():
        return send_from_directory(str(project_root), 'test_messages.html')
    else:
        return 'Тестовый файл не найден', 404