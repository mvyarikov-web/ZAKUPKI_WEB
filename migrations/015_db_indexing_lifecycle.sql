-- =====================================================================
-- Миграция для спецификации 015: Индексация в БД с управлением жизненным циклом
-- =====================================================================
-- Добавляет:
-- 1. Поля в таблицу documents: is_visible, deleted_at, last_accessed_at, access_count, indexing_cost_seconds
-- 2. Таблицу folder_index_status для отслеживания состояния индексации папок
-- 3. Индексы для оптимизации запросов
--
-- Дата: 2025-11-05
-- Increment: 015
-- =====================================================================

-- =====================================================================
-- 1. Расширение таблицы documents
-- =====================================================================

-- Добавляем поля для управления жизненным циклом
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE NOT NULL;

ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL;

ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP NULL;

ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0 NOT NULL;

ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS indexing_cost_seconds FLOAT NULL;

-- Обновляем существующие записи: устанавливаем last_accessed_at = indexed_at для старых документов
UPDATE documents 
SET last_accessed_at = indexed_at 
WHERE last_accessed_at IS NULL AND indexed_at IS NOT NULL;

-- =====================================================================
-- 2. Создание таблицы folder_index_status
-- =====================================================================

CREATE TABLE IF NOT EXISTS folder_index_status (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    folder_path TEXT NOT NULL,
    root_hash VARCHAR(64) NOT NULL,
    last_indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(owner_id, folder_path)
);

-- =====================================================================
-- 3. Индексы для оптимизации запросов
-- =====================================================================

-- Индекс для фильтрации по owner_id и is_visible (основной запрос поиска)
CREATE INDEX IF NOT EXISTS idx_documents_owner_visible 
ON documents(owner_id, is_visible);

-- Индекс для GC: поиск невидимых файлов старше N дней
CREATE INDEX IF NOT EXISTS idx_documents_deleted_at 
ON documents(deleted_at) 
WHERE is_visible = FALSE;

-- Индекс для расчёта retention score: активно используемые файлы
CREATE INDEX IF NOT EXISTS idx_documents_usage 
ON documents(owner_id, last_accessed_at) 
WHERE is_visible = TRUE;

-- Индекс для быстрого поиска статуса индексации папки
CREATE INDEX IF NOT EXISTS idx_folder_index_status_owner_path 
ON folder_index_status(owner_id, folder_path);

-- Индекс для полнотекстового поиска по чанкам (если ещё не существует)
-- Используется для гибридного поиска (FTS + векторный)
CREATE INDEX IF NOT EXISTS idx_chunks_text_fts 
ON chunks USING GIN (to_tsvector('russian', text));

-- =====================================================================
-- 4. Комментарии к новым полям (документация схемы)
-- =====================================================================

COMMENT ON COLUMN documents.is_visible IS 
'Флаг видимости: FALSE = мягко удалён, TRUE = активен';

COMMENT ON COLUMN documents.deleted_at IS 
'Временная метка мягкого удаления (NULL если не удалён)';

COMMENT ON COLUMN documents.last_accessed_at IS 
'Время последнего доступа к документу (для расчёта retention score)';

COMMENT ON COLUMN documents.access_count IS 
'Счётчик обращений к документу (для расчёта retention score)';

COMMENT ON COLUMN documents.indexing_cost_seconds IS 
'Стоимость индексации документа в секундах (учитывает OCR, извлечение текста)';

COMMENT ON TABLE folder_index_status IS 
'Отслеживание состояния индексации папок для инкрементальной индексации';

COMMENT ON COLUMN folder_index_status.root_hash IS 
'SHA256 от конкатенации (filename + mtime + size) всех файлов в папке';

-- =====================================================================
-- 5. Проверка миграции (вывод статистики)
-- =====================================================================

DO $$
DECLARE
    doc_count INTEGER;
    folder_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO doc_count FROM documents;
    SELECT COUNT(*) INTO folder_count FROM folder_index_status;
    
    RAISE NOTICE '✅ Миграция 015 завершена успешно';
    RAISE NOTICE 'Документов в БД: %', doc_count;
    RAISE NOTICE 'Папок в индексе: %', folder_count;
    RAISE NOTICE 'Новые поля documents: is_visible, deleted_at, last_accessed_at, access_count, indexing_cost_seconds';
    RAISE NOTICE 'Новая таблица: folder_index_status';
    RAISE NOTICE 'Добавлено индексов: 5 (owner_visible, deleted_at, usage, folder_path, text_fts)';
END $$;
