"""
Интеграционные тесты с реальными файлами из uploads.

Проверяет:
1. Индексация реальных файлов
2. Поиск по реальному контенту
3. Корректность извлечения текста из PDF/DOCX
"""
import pytest
import os
from pathlib import Path


@pytest.fixture
def uploads_path():
    """Путь к папке uploads с реальными файлами."""
    root = Path(__file__).parent.parent
    uploads = root / 'uploads'
    if not uploads.exists():
        pytest.skip('Папка uploads не найдена')
    return uploads


@pytest.fixture
def real_files(uploads_path):
    """Список реальных файлов в uploads."""
    files = []
    for root, dirs, filenames in os.walk(uploads_path):
        for fname in filenames:
            if fname == '_search_index.txt':
                continue
            full_path = os.path.join(root, fname)
            files.append(full_path)
    
    if not files:
        pytest.skip('Нет файлов в uploads')
    return files


def test_real_files_exist(real_files):
    """Проверка наличия реальных файлов."""
    assert len(real_files) > 0, "Должны быть реальные файлы в uploads"
    print(f"✅ Найдено {len(real_files)} файлов в uploads")
    
    # Показываем какие файлы найдены
    for f in real_files[:5]:  # первые 5
        print(f"  - {os.path.basename(f)}")


def test_extract_text_from_real_pdf(real_files):
    """Извлечение текста из реальных PDF файлов."""
    from document_processor.extractors.text_extractor import extract_text
    
    pdf_files = [f for f in real_files if f.lower().endswith('.pdf')]
    if not pdf_files:
        pytest.skip('Нет PDF файлов в uploads')
    
    success_count = 0
    for pdf_file in pdf_files:
        try:
            text = extract_text(pdf_file)
            if text and len(text.strip()) > 50:  # минимум 50 символов
                success_count += 1
                print(f"✅ {os.path.basename(pdf_file)}: извлечено {len(text)} символов")
            else:
                print(f"⚠️  {os.path.basename(pdf_file)}: текст пустой или короткий")
        except Exception as e:
            print(f"❌ {os.path.basename(pdf_file)}: ошибка {e}")
    
    assert success_count > 0, f"Должен быть хотя бы 1 успешно обработанный PDF (из {len(pdf_files)})"
    print(f"✅ Успешно обработано {success_count} из {len(pdf_files)} PDF файлов")


def test_extract_text_from_real_docx(real_files):
    """Извлечение текста из реальных DOCX файлов."""
    from document_processor.extractors.text_extractor import extract_text
    
    docx_files = [f for f in real_files if f.lower().endswith('.docx')]
    if not docx_files:
        pytest.skip('Нет DOCX файлов в uploads')
    
    success_count = 0
    for docx_file in docx_files:
        try:
            text = extract_text(docx_file)
            if text and len(text.strip()) > 50:
                success_count += 1
                print(f"✅ {os.path.basename(docx_file)}: извлечено {len(text)} символов")
            else:
                print(f"⚠️  {os.path.basename(docx_file)}: текст пустой или короткий")
        except Exception as e:
            print(f"❌ {os.path.basename(docx_file)}: ошибка {e}")
    
    assert success_count > 0, f"Должен быть хотя бы 1 успешно обработанный DOCX (из {len(docx_files)})"
    print(f"✅ Успешно обработано {success_count} из {len(docx_files)} DOCX файлов")


@pytest.mark.skipif(
    os.getenv('RUN_INTEGRATION_TESTS') != '1',
    reason='Интеграционный тест, требует RUN_INTEGRATION_TESTS=1'
)
def test_real_files_search_integration():
    """Полный цикл: проверка индексации и поиска через API."""
    import requests
    
    base_url = 'http://localhost:8081'
    headers = {'X-User-ID': '999', 'Content-Type': 'application/json'}
    
    # Проверяем статус индекса
    resp = requests.get(f'{base_url}/index_status', headers=headers)
    assert resp.status_code == 200, "API должен отвечать"
    
    data = resp.json()
    print(f"✅ Статус индекса: exists={data.get('exists')}, entries={data.get('entries')}")
    
    # Если нет документов — пропускаем
    if not data.get('exists') or data.get('entries', 0) == 0:
        pytest.skip('Нет проиндексированных документов для user_id=999')
    
    # Проверяем поиск
    test_terms = ['договор', 'требования', 'поставка', 'сплит']
    
    for term in test_terms:
        resp = requests.post(
            f'{base_url}/search',
            headers=headers,
            json={'search_terms': term}
        )
        
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            if results:
                print(f"✅ Найдено {len(results)} документов по запросу '{term}'")
                # Показываем первый результат
                first = results[0]
                print(f"  Файл: {first.get('file')}, совпадений: {first.get('match_count')}")
                return  # успешно нашли
    
    pytest.fail(f"Ни один из терминов {test_terms} не найден в проиндексированных документах")

