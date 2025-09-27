import os
import shutil
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
import docx
import openpyxl
import PyPDF2
import pdfplumber
import re
from flask import send_from_directory
import json
from datetime import datetime
from urllib.parse import unquote

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['SEARCH_RESULTS_FILE'] = 'uploads/search_results.json'

# Разрешенные расширения файлов
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}

# Статусы обработки файлов
file_status = {}  # filename: {'status': 'not_checked'|'processing'|'contains_keywords'|'no_keywords'|'error', 'result': {...}}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_search_results():
    """Сохранение результатов поиска в JSON файл"""
    try:
        data = {
            'last_updated': datetime.now().isoformat(),
            'file_status': file_status,
            'last_search_terms': getattr(save_search_results, 'last_terms', ''),
        }
        
        os.makedirs(os.path.dirname(app.config['SEARCH_RESULTS_FILE']), exist_ok=True)
        with open(app.config['SEARCH_RESULTS_FILE'], 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Результаты сохранены в {app.config['SEARCH_RESULTS_FILE']}")
    except Exception as e:
        print(f"Ошибка сохранения результатов: {str(e)}")

def load_search_results():
    """Загрузка результатов поиска из JSON файла"""
    global file_status
    try:
        if os.path.exists(app.config['SEARCH_RESULTS_FILE']):
            with open(app.config['SEARCH_RESULTS_FILE'], 'r', encoding='utf-8') as f:
                data = json.load(f)
                file_status = data.get('file_status', {})
                save_search_results.last_terms = data.get('last_search_terms', '')
                print(f"Результаты загружены из {app.config['SEARCH_RESULTS_FILE']}")
                print(f"Загружено статусов: {len(file_status)}")
                return data.get('last_search_terms', '')
    except Exception as e:
        print(f"Ошибка загрузки результатов: {str(e)}")
        file_status = {}
    return ''

def clear_search_results():
    """Очистка файла с результатами поиска"""
    global file_status
    try:
        if os.path.exists(app.config['SEARCH_RESULTS_FILE']):
            os.remove(app.config['SEARCH_RESULTS_FILE'])
        file_status = {}
        print("Результаты поиска очищены")
        return True
    except Exception as e:
        print(f"Ошибка очистки результатов: {str(e)}")
        return False

def extract_text_from_pdf(file_path):
    """Извлечение текста из PDF файла"""
    text = ""
    try:
        # Попробуем pdfplumber сначала (лучше для сложных PDF)
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except:
        try:
            # Если pdfplumber не работает, попробуем PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except:
            text = "Ошибка извлечения текста из PDF"
    
    return text

def extract_text_from_docx(file_path):
    """Извлечение текста из DOCX файла"""
    try:
        doc = docx.Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        print(f"Ошибка при чтении DOCX файла {file_path}: {str(e)}")
        return "Ошибка извлечения текста из DOCX"

def extract_text_from_doc(file_path):
    """Извлечение текста из DOC файла (старый формат)"""
    # python-docx не поддерживает .doc файлы (только .docx)
    return "Формат .doc не поддерживается. Пожалуйста, конвертируйте файл в .docx"

def extract_text_from_xlsx(file_path):
    """Извлечение текста из XLSX файла"""
    try:
        workbook = openpyxl.load_workbook(file_path)
        text = ""
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            text += f"Лист: {sheet_name}\n"
            for row in sheet.iter_rows():
                row_text = []
                for cell in row:
                    if cell.value is not None:
                        row_text.append(str(cell.value))
                if row_text:
                    text += " | ".join(row_text) + "\n"
        return text
    except Exception as e:
        print(f"Ошибка при чтении XLSX файла {file_path}: {str(e)}")
        return "Ошибка извлечения текста из XLSX"

def extract_text_from_xls(file_path):
    """Извлечение текста из XLS файла (старый формат)"""
    # openpyxl не поддерживает .xls файлы (только .xlsx)
    return "Формат .xls не поддерживается. Пожалуйста, конвертируйте файл в .xlsx"

def extract_text_from_txt(file_path):
    """Извлечение текста из TXT файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='cp1251') as file:
                return file.read()
        except:
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    return file.read()
            except:
                return "Ошибка извлечения текста из TXT"
    except:
        return "Ошибка извлечения текста из TXT"

def extract_text_from_file(file_path):
    """Универсальная функция для извлечения текста из различных форматов"""
    file_extension = file_path.rsplit('.', 1)[1].lower()
    
    try:
        if file_extension == 'pdf':
            return extract_text_from_pdf(file_path)
        elif file_extension == 'docx':
            return extract_text_from_docx(file_path)
        elif file_extension == 'doc':
            return extract_text_from_doc(file_path)
        elif file_extension == 'xlsx':
            return extract_text_from_xlsx(file_path)
        elif file_extension == 'xls':
            return extract_text_from_xls(file_path)
        elif file_extension == 'txt':
            return extract_text_from_txt(file_path)
        else:
            return "Неподдерживаемый формат файла"
    except Exception as e:
        print(f"Общая ошибка при обработке файла {file_path}: {str(e)}")
        return f"Ошибка обработки файла: {str(e)}"

def search_in_files(search_terms):
    """Поиск по ключевым словам во всех загруженных файлах"""
    results = []
    search_terms_lower = [term.lower().strip() for term in search_terms.split(',') if term.strip()]
    
    if not search_terms_lower:
        return results
    
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        if allowed_file(filename):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                text_content = extract_text_from_file(file_path)
                text_content_lower = text_content.lower()
                
                # Проверяем наличие каждого ключевого слова
                found_terms = []
                for term in search_terms_lower:
                    if term in text_content_lower:
                        found_terms.append(term)
                
                if found_terms:
                    # Найдем контекст вокруг найденных терминов
                    context_snippets = []
                    for term in found_terms:
                        pattern = re.compile(re.escape(term), re.IGNORECASE)
                        matches = pattern.finditer(text_content)
                        for match in matches:
                            start = max(0, match.start() - 50)
                            end = min(len(text_content), match.end() + 50)
                            snippet = text_content[start:end].strip()
                            context_snippets.append(f"...{snippet}...")
                            break  # Только первое вхождение для каждого термина
                    
                    results.append({
                        'filename': filename,
                        'found_terms': found_terms,
                        'context': context_snippets[:3]  # Ограничим до 3 контекстов
                    })
            except Exception as e:
                print(f"Ошибка обработки файла {filename}: {str(e)}")
    
    return results

@app.route('/')
def index():
    """Главная страница"""
    # Загружаем сохраненные результаты поиска
    last_search_terms = load_search_results()
    
    # Получаем список загруженных файлов с группировкой по папкам
    files_by_folder = {}
    total_files = 0
    
    print(f"Проверяем папку: {app.config['UPLOAD_FOLDER']}")  # Отладка
    
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        # Рекурсивно обходим все файлы и папки
        for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER']):
            for filename in files:
                if allowed_file(filename):
                    file_path = os.path.join(root, filename)
                    # Определяем относительную папку
                    relative_folder = os.path.relpath(root, app.config['UPLOAD_FOLDER'])
                    
                    # Правильно определяем название папки
                    if relative_folder == '.':
                        # Файлы в корневой папке uploads
                        folder_display_name = '📁 Корневая папка'
                        folder_key = 'root'
                    else:
                        # Файлы в подпапках - берем последнюю часть пути
                        folder_parts = relative_folder.split(os.sep)
                        folder_display_name = f'📂 {folder_parts[-1]}'
                        folder_key = relative_folder
                    
                    file_size = os.path.getsize(file_path)
                    # Получаем статус файла из новой структуры данных
                    file_key = os.path.join(relative_folder, filename) if relative_folder != '.' else filename
                    file_data = file_status.get(file_key, {})
                    status = file_data.get('status', 'not_checked')
                    
                    file_info = {
                        'name': filename,
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
                    
                    print(f"Добавлен файл: {filename} в папку {folder_display_name}, размер: {file_size}, статус: {status}")  # Отладка
    else:
        print("Папка uploads не существует")  # Отладка
    
    print(f"Всего файлов для отображения: {total_files}, папок: {len(files_by_folder)}")  # Отладка
    return render_template('index.html', files_by_folder=files_by_folder, total_files=total_files, last_search_terms=last_search_terms)

@app.route('/upload', methods=['POST'])
def upload_files():
    """Обработка загрузки файлов"""
    if 'files' not in request.files:
        return jsonify({'error': 'Файлы не выбраны'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    
    for file in files:
        if file and file.filename != '':
            original_filename = file.filename
            print(f"Загружается файл: {original_filename}")  # Отладка
            
            if allowed_file(original_filename):
                # Обрабатываем путь из webkitRelativePath если есть (для папок)
                relative_path = request.form.get('webkitRelativePath', '')
                if not relative_path:
                    # Пытаемся получить путь из самого файла (если поддерживается браузером)
                    relative_path = getattr(file, 'filename', original_filename)
                
                # Разделяем путь на папки и имя файла
                path_parts = relative_path.split('/') if '/' in relative_path else [relative_path]
                filename = path_parts[-1]  # Последняя часть - имя файла
                folder_parts = path_parts[:-1]  # Все предыдущие части - путь к папке
                
                # Создаем безопасные имена для папок и файла
                safe_folder_parts = [secure_filename(part) for part in folder_parts if part]
                safe_filename = secure_filename(filename)
                
                # Восстанавливаем расширение если secure_filename его удалил
                if '.' not in safe_filename and '.' in filename:
                    extension = filename.rsplit('.', 1)[1].lower()
                    safe_filename = safe_filename + '.' + extension
                
                # Создаем полный путь к папке
                if safe_folder_parts:
                    target_folder = os.path.join(app.config['UPLOAD_FOLDER'], *safe_folder_parts)
                    os.makedirs(target_folder, exist_ok=True)
                else:
                    target_folder = app.config['UPLOAD_FOLDER']
                
                # Проверяем уникальность имени файла
                counter = 1
                base_name, extension = os.path.splitext(safe_filename) if '.' in safe_filename else (safe_filename, '')
                final_filename = safe_filename
                
                while os.path.exists(os.path.join(target_folder, final_filename)):
                    final_filename = f"{base_name}_{counter}{extension}"
                    counter += 1
                
                # Сохраняем файл
                file_path = os.path.join(target_folder, final_filename)
                file.save(file_path)
                
                # Устанавливаем статус "не проверено" для новых файлов
                # Используем относительный путь как ключ для уникальности
                file_key = os.path.join(*safe_folder_parts, final_filename) if safe_folder_parts else final_filename
                file_status[file_key] = {'status': 'not_checked', 'result': None}
                uploaded_files.append(final_filename)
                
                print(f"Файл сохранен: {file_path}, ключ: {file_key}")  # Отладка
            else:
                return jsonify({'error': f'Неподдерживаемый тип файла: {original_filename}'}), 400
    
    print(f"Загружено файлов: {len(uploaded_files)}")  # Отладка
    return jsonify({'success': True, 'uploaded_files': uploaded_files})

@app.route('/search', methods=['POST'])
def search():
    """Поиск по ключевым словам"""
    search_terms = request.json.get('search_terms', '')
    
    if not search_terms.strip():
        return jsonify({'error': 'Введите ключевые слова для поиска'}), 400
    
    results = []
    
    # Проверяем существование папки uploads
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        print("Папка uploads не существует при поиске")
        return jsonify({'results': results})
    
    # Получаем список файлов для обработки (рекурсивно)
    files_to_search = []
    for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER']):
        for filename in files:
            if allowed_file(filename):
                # Создаем относительный путь от uploads
                rel_path = os.path.relpath(os.path.join(root, filename), app.config['UPLOAD_FOLDER'])
                files_to_search.append(rel_path)
    
    print(f"Поиск в файлах: {files_to_search}")
    
    # Обрабатываем каждый файл
    for file_rel_path in files_to_search:
        print(f"Обрабатываем файл: {file_rel_path}")
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_rel_path)
        filename = os.path.basename(file_rel_path)
        
        if not os.path.exists(file_path):
            print(f"Файл {file_rel_path} не найден")
            continue
            
        file_status[file_rel_path] = {'status': 'processing'}
        try:
            print(f"Извлекаем текст из {file_rel_path}")
            text_content = extract_text_from_file(file_path)
            print(f"Длина извлеченного текста: {len(text_content)} символов")
            
            text_content_lower = text_content.lower()
            search_terms_lower = [term.lower().strip() for term in search_terms.split(',') if term.strip()]
            found_terms = []
            context_snippets = []
            
            for term in search_terms_lower:
                if term in text_content_lower:
                    found_terms.append(term)
                    print(f"Найден термин '{term}' в файле {file_rel_path}")
                    # Найти предложения с этим термином
                    sentences = re.split(r'(?<=[.!?])\s+', text_content)
                    for sentence in sentences:
                        if re.search(re.escape(term), sentence, re.IGNORECASE):
                            context_snippets.append(sentence.strip())
                            break
            
            # Сохраняем статус файла с правильным ключом
            if found_terms:
                file_status[file_rel_path] = {
                    'status': 'contains_keywords',
                    'found_terms': found_terms,
                    'context': context_snippets[:5],
                    'processed_at': datetime.now().isoformat()
                }
                results.append({
                    'filename': filename,
                    'found_terms': found_terms,
                    'context': context_snippets[:3]
                })
            else:
                file_status[file_rel_path] = {
                    'status': 'no_keywords', 
                    'processed_at': datetime.now().isoformat()
                }
        except Exception as e:
            print(f"Ошибка при обработке файла {file_rel_path}: {str(e)}")
            file_status[file_rel_path] = {
                'status': 'error', 
                'error': str(e),
                'processed_at': datetime.now().isoformat()
            }
    
    # Сохраняем результаты поиска
    save_search_results.last_terms = search_terms
    save_search_results()
    
    return jsonify({'results': results})

@app.route('/delete/<path:filepath>', methods=['DELETE'])
def delete_file(filepath):
    """Удаление файла"""
    try:
        # Декодируем URL-кодированный путь к файлу
        from urllib.parse import unquote
        decoded_filepath = unquote(filepath)
        print(f"Попытка удалить файл: {decoded_filepath}")
        
        # Проверяем, что это не попытка выйти за пределы папки uploads
        if '..' in decoded_filepath or decoded_filepath.startswith('/'):
            return jsonify({'error': 'Недопустимый путь к файлу'}), 400
        
        # Полный путь к файлу
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], decoded_filepath)
        print(f"Полный путь к файлу: {file_path}")
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            # Удаляем из статусов файлов все возможные варианты ключей
            file_status.pop(decoded_filepath, None)
            file_status.pop(os.path.basename(decoded_filepath), None)
            
            # Сохраняем обновленные результаты
            save_search_results()
            print(f"Файл {decoded_filepath} успешно удален")
            return jsonify({'success': True})
        else:
            print(f"Файл не найден: {file_path}")
            return jsonify({'error': 'Файл не найден'}), 404
            
    except Exception as e:
        print(f"Ошибка при удалении файла: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete_folder/<path:folder_path>', methods=['DELETE'])
def delete_folder(folder_path):
    """Удаление папки со всеми файлами"""
    try:
        from urllib.parse import unquote
        decoded_folder_path = unquote(folder_path)
        print(f"Попытка удалить папку: {decoded_folder_path}")
        
        # Проверяем безопасность пути
        if '..' in decoded_folder_path or decoded_folder_path.startswith('/'):
            return jsonify({'error': 'Недопустимый путь к папке'}), 400
        
        if decoded_folder_path == 'root':
            # Удаление всех файлов из корневой папки uploads
            target_folder = app.config['UPLOAD_FOLDER']
            deleted_files = []
            
            if os.path.exists(target_folder):
                for item in os.listdir(target_folder):
                    item_path = os.path.join(target_folder, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_files.append(item)
                        # Удаляем из статусов
                        file_status.pop(item, None)
                        
            message = f'Удалено {len(deleted_files)} файлов из корневой папки'
        else:
            # Удаление подпапки
            target_folder = os.path.join(app.config['UPLOAD_FOLDER'], decoded_folder_path)
            
            if not os.path.exists(target_folder):
                return jsonify({'error': 'Папка не найдена'}), 404
            
            # Собираем список файлов для удаления из статусов
            files_to_remove_from_status = []
            for root, dirs, files in os.walk(target_folder):
                for filename in files:
                    rel_path = os.path.relpath(os.path.join(root, filename), app.config['UPLOAD_FOLDER'])
                    files_to_remove_from_status.append(rel_path)
            
            # Удаляем папку рекурсивно
            shutil.rmtree(target_folder)
            
            # Удаляем файлы из статусов
            for file_key in files_to_remove_from_status:
                file_status.pop(file_key, None)
                file_status.pop(os.path.basename(file_key), None)
            
            message = f'Папка "{decoded_folder_path}" успешно удалена'
        
        # Сохраняем обновленные результаты
        save_search_results()
        print(message)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        print(f"Ошибка при удалении папки: {str(e)}")
        return jsonify({'error': f'Ошибка удаления папки: {str(e)}'}), 500

# Страница с результатом обработки файла
@app.route('/result/<path:filepath>')
def result_page(filepath):
    """Отображение результатов обработки файла"""
    # Декодируем путь к файлу
    from urllib.parse import unquote
    decoded_filepath = unquote(filepath)
    
    print(f"Ищем результаты для файла: {decoded_filepath}")
    
    # Пробуем найти результат по полному пути
    result = file_status.get(decoded_filepath, {})
    
    # Если не найден, пробуем по короткому имени файла
    if not result:
        short_filename = os.path.basename(decoded_filepath)
        result = file_status.get(short_filename, {})
        print(f"Поиск по короткому имени {short_filename}: найдено={bool(result)}")
    
    # Если все еще не найден, пробуем найти любой файл с таким же именем
    if not result:
        for key, data in file_status.items():
            if os.path.basename(key) == os.path.basename(decoded_filepath):
                result = data
                decoded_filepath = key  # Обновляем путь на найденный
                print(f"Найден результат по базовому имени: {key}")
                break
    
    status = result.get('status', 'not_checked')
    
    # Получаем данные результата в зависимости от структуры
    if 'found_terms' in result:
        # Новая структура
        found_terms = result.get('found_terms', [])
        context = result.get('context', [])
        data = {
            'filename': os.path.basename(decoded_filepath),
            'found_terms': found_terms,
            'context': context
        }
    else:
        # Старая структура
        data = result.get('result', None)
    
    # Получаем последние ключевые слова для подсветки
    last_terms = getattr(save_search_results, 'last_terms', '')
    
    print(f"Результат для {decoded_filepath}: status={status}, data={bool(data)}")
    
    return render_template('result.html', 
                         filename=os.path.basename(decoded_filepath), 
                         filepath=decoded_filepath,
                         status=status, 
                         data=data, 
                         search_terms=last_terms)

# Очистка результатов поиска
@app.route('/clear_results', methods=['POST'])
def clear_results():
    """Очистка всех сохраненных результатов поиска"""
    if clear_search_results():
        return jsonify({'success': True, 'message': 'Результаты поиска успешно очищены'})
    else:
        return jsonify({'success': False, 'message': 'Ошибка очистки результатов'})

# Создаем папку для загрузок если её нет
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Инициализируем атрибут для сохранения последних ключевых слов
    save_search_results.last_terms = ''
    
    app.run(debug=True, host='127.0.0.1', port=5000)