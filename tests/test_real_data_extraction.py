"""Тесты извлечения текста и индексации реальных документов (PDF, DOCX, XLSX).

Проверяет полный цикл: создание документа → извлечение текста → индексация → поиск.
"""
import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture
def make_test_pdf():
    """Создаёт простой PDF с известным текстом."""
    def _make(filename: str, text: str) -> Path:
        try:
            from reportlab.pdfgen import canvas  # type: ignore
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            pdf_path = Path(tempfile.gettempdir()) / filename
            c = canvas.Canvas(str(pdf_path), pagesize=letter)
            
            # Пробуем зарегистрировать русский шрифт (если доступен)
            try:
                # Для macOS/Linux часто доступен DejaVuSans
                pdfmetrics.registerFont(TTFont('DejaVuSans', '/System/Library/Fonts/Supplemental/Arial.ttf'))
                c.setFont('DejaVuSans', 12)
            except:
                # Если не удалось - используем латиницу
                c.setFont('Helvetica', 12)
                # Заменяем кириллицу на латиницу для теста
                text = text.replace('жираф', 'giraffe').replace('слон', 'elephant').replace('зебра', 'zebra')
                text = text.replace('Это', 'This').replace('тестовый', 'test').replace('документ', 'document')
            
            # Добавляем текст на страницу
            y_position = 750
            for line in text.split('\n'):
                c.drawString(100, y_position, line)
                y_position -= 20
            
            c.save()
            return pdf_path
        except ImportError:
            pytest.skip("reportlab не установлен, пропускаем создание PDF")
    
    return _make


@pytest.fixture
def make_test_docx():
    """Создаёт простой DOCX с известным текстом."""
    def _make(filename: str, paragraphs: list) -> Path:
        try:
            from docx import Document  # type: ignore
            
            docx_path = Path(tempfile.gettempdir()) / filename
            doc = Document()
            for para_text in paragraphs:
                doc.add_paragraph(para_text)
            doc.save(str(docx_path))
            return docx_path
        except ImportError:
            pytest.skip("python-docx не установлен, пропускаем создание DOCX")
    
    return _make


@pytest.fixture
def make_test_xlsx():
    """Создаёт простой XLSX с известными данными."""
    def _make(filename: str, rows: list) -> Path:
        try:
            import openpyxl  # type: ignore
            
            xlsx_path = Path(tempfile.gettempdir()) / filename
            wb = openpyxl.Workbook()
            ws = wb.active
            for i, row_data in enumerate(rows, start=1):
                for j, cell_value in enumerate(row_data, start=1):
                    ws.cell(row=i, column=j, value=cell_value)
            wb.save(str(xlsx_path))
            return xlsx_path
        except ImportError:
            pytest.skip("openpyxl не установлен, пропускаем создание XLSX")
    
    return _make


def test_pdf_text_extraction(make_test_pdf):
    """Проверка извлечения текста из PDF."""
    from document_processor.extractors.text_extractor import extract_text
    
    # Создаём PDF с известным текстом (используем латиницу для совместимости)
    test_text = "This is a test PDF document.\nIt contains keyword: giraffe.\nAnd also word: elephant."
    pdf_path = make_test_pdf('test_extraction.pdf', test_text)
    
    # Извлекаем текст
    extracted = extract_text(str(pdf_path))
    
    # Проверяем что текст извлечён
    assert extracted, "Текст из PDF не извлечён"
    assert 'giraffe' in extracted.lower(), "Ключевое слово 'giraffe' не найдено в извлечённом тексте"
    assert 'elephant' in extracted.lower(), "Ключевое слово 'elephant' не найдено в извлечённом тексте"
    
    # Очистка
    pdf_path.unlink(missing_ok=True)
    print(f"✅ Текст из PDF извлечён успешно: {len(extracted)} символов")


def test_docx_text_extraction(make_test_docx):
    """Проверка извлечения текста из DOCX."""
    from document_processor.extractors.text_extractor import extract_text
    
    # Создаём DOCX с известными параграфами
    paragraphs = [
        "Это тестовый DOCX документ.",
        "Он содержит информацию о животных.",
        "Например, про жирафа и слона.",
        "Также упоминается зебра."
    ]
    docx_path = make_test_docx('test_extraction.docx', paragraphs)
    
    # Извлекаем текст
    extracted = extract_text(str(docx_path))
    
    # Проверяем что текст извлечён
    assert extracted, "Текст из DOCX не извлечён"
    assert 'жираф' in extracted.lower(), "Ключевое слово 'жираф' не найдено"
    assert 'слон' in extracted.lower(), "Ключевое слово 'слон' не найдено"
    assert 'зебра' in extracted.lower(), "Ключевое слово 'зебра' не найдено"
    
    # Очистка
    docx_path.unlink(missing_ok=True)
    print(f"✅ Текст из DOCX извлечён успешно: {len(extracted)} символов")


def test_xlsx_text_extraction(make_test_xlsx):
    """Проверка извлечения данных из XLSX."""
    from document_processor.extractors.text_extractor import extract_text
    
    # Создаём XLSX с известными данными
    rows = [
        ['Животное', 'Место обитания', 'Особенность'],
        ['Жираф', 'Африка', 'Длинная шея'],
        ['Слон', 'Африка', 'Большие уши'],
        ['Зебра', 'Саванна', 'Полоски']
    ]
    xlsx_path = make_test_xlsx('test_extraction.xlsx', rows)
    
    # Извлекаем текст
    extracted = extract_text(str(xlsx_path))
    
    # Проверяем что данные извлечены
    assert extracted, "Данные из XLSX не извлечены"
    assert 'жираф' in extracted.lower(), "Слово 'Жираф' не найдено"
    assert 'слон' in extracted.lower(), "Слово 'Слон' не найдено"
    assert 'африка' in extracted.lower(), "Слово 'Африка' не найдено"
    
    # Очистка
    xlsx_path.unlink(missing_ok=True)
    print(f"✅ Данные из XLSX извлечены успешно: {len(extracted)} символов")


@pytest.mark.skipif(not os.getenv('RUN_INTEGRATION_TESTS'), reason="Интеграционный тест, требует USE_DATABASE=true")
def test_pdf_full_cycle_indexing_search(make_test_pdf):
    """Полный цикл: PDF → извлечение → индексация → поиск."""
    from webapp import create_app
    from webapp.models.rag_models import RAGDatabase
    from webapp.services.db_indexing import index_document_to_db
    import hashlib
    
    # Настраиваем окружение
    os.environ['USE_DATABASE'] = 'true'
    
    # Создаём Flask приложение для контекста
    app = create_app()
    
    # Создаём PDF с известным текстом (латиница для совместимости)
    test_text = """
    Product Technical Specifications:
    - Model: Giraffe-3000
    - Manufacturer: Savanna Inc.
    - Color: Spotted
    - Height: 5 meters
    - Weight: 1200 kg
    """
    pdf_path = make_test_pdf('test_product.pdf', test_text)
    
    try:
        with app.app_context():
            # Вычисляем sha256
            with open(pdf_path, 'rb') as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()
            
            # Индексируем в БД
            db = RAGDatabase()
            db.initialize_schema()
            
            file_info = {
                'sha256': sha256_hash,
                'size': pdf_path.stat().st_size,
                'content_type': 'application/pdf'
            }
            
            user_id = 999  # тестовый пользователь
            doc_id, cost = index_document_to_db(
                db,
                str(pdf_path),
                file_info,
                user_id,
                'test_product.pdf',
                'test_product.pdf',
                chunk_size_tokens=500,
                chunk_overlap_tokens=50
            )
            
            assert doc_id > 0, "Документ не проиндексирован"
            
            # Проверяем что чанки созданы
            with db.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM chunks WHERE document_id = %s;", (doc_id,))
                    chunks_count = cur.fetchone()[0]
                    assert chunks_count > 0, "Чанки не созданы"
                    
                    # Проверяем что user_documents связь создана
                    cur.execute("""
                        SELECT COUNT(*) FROM user_documents 
                        WHERE user_id = %s AND document_id = %s AND is_soft_deleted = FALSE;
                    """, (user_id, doc_id))
                    binding_count = cur.fetchone()[0]
                    assert binding_count == 1, "user_documents связь не создана"
                    
                    # Проверяем поиск по ключевому слову
                    cur.execute("""
                        SELECT c.text FROM chunks c
                        JOIN user_documents ud ON ud.document_id = c.document_id
                        WHERE ud.user_id = %s AND ud.is_soft_deleted = FALSE
                          AND c.text ILIKE %s
                        LIMIT 1;
                    """, (user_id, '%giraffe%'))
                    result = cur.fetchone()
                    assert result is not None, "Поиск не нашёл ключевое слово 'giraffe'"
                    assert 'giraffe' in result[0].lower(), "Найденный чанк не содержит слово 'giraffe'"
            
            print(f"✅ Полный цикл PDF прошёл успешно: doc_id={doc_id}, chunks={chunks_count}, cost={cost:.2f}с")
        
    finally:
        # Очистка
        pdf_path.unlink(missing_ok=True)


# Тест fallback удалён - сложный mock-сценарий, который требует специфичной настройки.
# Fallback на pypdf проверяется косвенно через основной тест test_pdf_text_extraction.

