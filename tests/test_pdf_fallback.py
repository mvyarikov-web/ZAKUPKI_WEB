import os
import hashlib
import tempfile
from pathlib import Path

import pytest
from flask import current_app

from webapp.models.rag_models import RAGDatabase
from webapp.services.db_indexing import index_document_to_db

@pytest.mark.integration
def test_pdf_empty_fallback(app):
    """Проверка: пустой или нераспознанный PDF индексируется с fallback-чанком."""
    cfg = app.config
    db = current_app.extensions.get('rag_db_test')  # может отсутствовать, создаём новый
    if db is None:
        from webapp.models.rag_models import RAGDatabase
        db = RAGDatabase(cfg['DATABASE_URL'].replace('postgresql+psycopg2://', 'postgresql://'))
        current_app.extensions['rag_db_test'] = db

    # создаём фиктивный PDF (минимальная структура PDF с почти пустым контентом)
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\n2 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / 'empty.pdf'
        pdf_path.write_bytes(pdf_bytes)
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        file_info = {
            'sha256': sha256,
            'size': pdf_path.stat().st_size,
            'content_type': 'application/pdf'
        }
        doc_id, cost = index_document_to_db(
            db=db,
            file_path=str(pdf_path),
            file_info=file_info,
            user_id=1,
            original_filename='empty.pdf',
            user_path='empty.pdf',
            chunk_size_tokens=256,
            chunk_overlap_tokens=0
        )
        assert doc_id > 0
        # Проверяем что хотя бы один чанк создан и содержит placeholder
        with db.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT text FROM chunks WHERE document_id = %s;", (doc_id,))
                rows = cur.fetchall()
        assert rows, 'Чанки не созданы'
        texts = [r[0] for r in rows]
        assert any('[ПУСТОЙ PDF ИЛИ ОШИБКА ИЗВЛЕЧЕНИЯ]' in t for t in texts), 'Fallback для пустого PDF не сработал'
