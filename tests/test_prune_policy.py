import os
import uuid
from io import BytesIO
from werkzeug.datastructures import FileStorage
from sqlalchemy import text

from webapp.services.blob_storage_service import BlobStorageService
from webapp.config.config_service import ConfigService


def test_prune_policy(db, test_user, monkeypatch):
    """Тест: prune удаляет 30% документов при превышении лимита."""
    # Очистка БД перед тестом
    db.execute(text("DELETE FROM chunks"))
    db.execute(text("DELETE FROM search_index"))
    db.execute(text("DELETE FROM user_documents"))
    db.execute(text("DELETE FROM documents"))
    db.commit()
    
    # Установим малый лимит (2 KB) через app_settings (приоритет над env)
    db.execute(text("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('DB_SIZE_LIMIT_BYTES', '2048', NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """))
    db.commit()
    
    # Также обновим env для ConfigService fallback
    monkeypatch.setenv('DB_SIZE_LIMIT_BYTES', '2048')
    config = ConfigService()
    service = BlobStorageService(config)

    # Создадим 10 маленьких файлов по ~310 байт (в сумме ~3100 байт)
    contents = [f"file {i} " + ("x" * 300) for i in range(10)]
    created_ids = []
    
    # Загружаем файлы, некоторые могут вызвать RuntimeError если после prune места нет
    for c in contents:
        try:
            buf = BytesIO(c.encode('utf-8'))
            fs = FileStorage(stream=buf, filename=f"f_{uuid.uuid4().hex[:6]}.txt", content_type='text/plain')
            doc, is_new = service.save_file_to_db(db=db, file=fs, user_id=test_user.id, user_path=f"test/{fs.filename}")
            created_ids.append(doc.id)
        except RuntimeError as e:
            # Ожидаемо: после prune не удалось освободить место
            assert 'Недостаточно места' in str(e)
            break

    # После создания должно быть применено prune - суммарный размер <= лимит
    total = db.execute(text("SELECT COALESCE(SUM(size_bytes),0) FROM documents WHERE blob IS NOT NULL")).scalar()
    
    # Читаем лимит из БД
    limit_from_db = int(db.execute(text("SELECT value FROM app_settings WHERE key = 'DB_SIZE_LIMIT_BYTES'")).scalar())
    
    assert total <= limit_from_db, f"Размер {total} превышает лимит {limit_from_db}"

    # Проверим что были созданы документы, но не все 10 (т.к. prune ограничил)
    count = db.execute(text("SELECT COUNT(*) FROM documents WHERE blob IS NOT NULL")).scalar()
    assert count > 0, "Должен быть создан хотя бы один документ"
    assert count < len(contents), f"Ожидалось меньше {len(contents)} документов, получено {count}"
    
    # Восстанавливаем дефолтный лимит после теста
    db.execute(text("""
        UPDATE app_settings 
        SET value = '10737418240' 
        WHERE key = 'DB_SIZE_LIMIT_BYTES'
    """))
    db.commit()
