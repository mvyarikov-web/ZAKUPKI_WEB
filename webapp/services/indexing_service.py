"""
Сервис индексации документов с генерацией embeddings.
"""
import hashlib
from typing import List, Optional, Tuple
import openai

from webapp.db.repositories import DocumentRepository, ChunkRepository
from webapp.db.models import Document


class IndexingService:
    """
    Сервис для индексации документов:
    - Извлечение текста из Document.blob
    - Разбивка на чанки
    - Генерация embeddings через OpenAI
    - Сохранение в chunks с pgvector
    """
    
    # Параметры чанкинга
    CHUNK_SIZE = 512  # Размер чанка в токенах (примерно)
    CHUNK_OVERLAP = 50  # Перекрытие между чанками
    MAX_CHARS_PER_CHUNK = 2000  # Макс. символов на чанк
    
    # OpenAI
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS = 1536
    
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        openai_api_key: Optional[str] = None
    ):
        """
        Args:
            document_repo: DocumentRepository
            chunk_repo: ChunkRepository
            openai_api_key: OpenAI API ключ (опционально)
        """
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        
        if openai_api_key:
            openai.api_key = openai_api_key
    
    @staticmethod
    def extract_text_from_blob(document: Document) -> str:
        """
        Извлечь текст из Document.blob.
        
        Для простоты пока поддерживаем только текстовые файлы.
        Для PDF/DOCX нужна дополнительная обработка через document_processor.
        
        Args:
            document: Document с заполненным blob
            
        Returns:
            Извлечённый текст
        """
        if not document.blob:
            return ""
        
        # Простое декодирование для текстовых файлов
        try:
            text = document.blob.decode('utf-8')
        except UnicodeDecodeError:
            # Пробуем другие кодировки
            try:
                text = document.blob.decode('cp1251')
            except UnicodeDecodeError:
                try:
                    text = document.blob.decode('latin-1')
                except UnicodeDecodeError:
                    text = ""
        
        return text.strip()
    
    @staticmethod
    def split_into_chunks(text: str, chunk_size: int = MAX_CHARS_PER_CHUNK) -> List[str]:
        """
        Разбить текст на чанки с перекрытием.
        
        Args:
            text: Исходный текст
            chunk_size: Размер чанка в символах
            
        Returns:
            Список текстовых чанков
        """
        if not text:
            return []
        
        chunks = []
        
        # Разбиваем по предложениям для более естественных границ
        sentences = text.split('. ')
        
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        # Добавляем последний чанк
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    @staticmethod
    def calculate_text_hash(text: str) -> str:
        """
        Рассчитать SHA256 хэш текста для дедупликации.
        
        Args:
            text: Текст чанка
            
        Returns:
            SHA256 хэш
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Сгенерировать embeddings через OpenAI API.
        
        Args:
            texts: Список текстов
            
        Returns:
            Список векторов embeddings (1536 размерность)
        """
        if not texts:
            return []
        
        try:
            response = openai.embeddings.create(
                input=texts,
                model=self.EMBEDDING_MODEL
            )
            
            embeddings = [item.embedding for item in response.data]
            return embeddings
        
        except Exception as e:
            # При ошибке возвращаем пустые векторы
            print(f"Ошибка генерации embeddings: {e}")
            return [[0.0] * self.EMBEDDING_DIMENSIONS for _ in texts]
    
    def index_document(
        self,
        document_id: int,
        reindex: bool = False
    ) -> Tuple[int, Optional[str]]:
        """
        Индексировать документ: извлечь текст, разбить на чанки, сгенерировать embeddings.
        
        Args:
            document_id: ID документа
            reindex: Переиндексировать (удалить старые чанки)
            
        Returns:
            (количество_чанков, error_message)
        """
        # Получаем документ
        document = self.document_repo.get_by_id(document_id)
        if not document:
            return 0, f"Документ {document_id} не найден"
        
        # Удаляем старые чанки при переиндексации
        if reindex:
            self.chunk_repo.delete_by_document(document_id)
        
        # Извлекаем текст
        text = self.extract_text_from_blob(document)
        if not text:
            return 0, "Не удалось извлечь текст из документа"
        
        # Разбиваем на чанки
        chunks_text = self.split_into_chunks(text)
        if not chunks_text:
            return 0, "Не удалось разбить текст на чанки"
        
        # Генерируем embeddings
        embeddings = self.generate_embeddings(chunks_text)
        
        # Сохраняем чанки
        chunks_data = []
        for idx, (chunk_text, embedding) in enumerate(zip(chunks_text, embeddings)):
            chunks_data.append({
                'document_id': document_id,
                'owner_id': document.owner_id,
                'text': chunk_text,
                'chunk_idx': idx,
                'embedding': embedding,
                'text_sha256': self.calculate_text_hash(chunk_text),
                'tokens': len(chunk_text.split())  # Примерная оценка
            })
        
        # Bulk insert
        try:
            created_chunks = self.chunk_repo.create_many(chunks_data)
            
            # Обновляем статус документа
            self.document_repo.mark_indexed(document_id, len(created_chunks))
            
            return len(created_chunks), None
        
        except Exception as e:
            # Помечаем документ как failed
            self.document_repo.mark_failed(document_id)
            return 0, f"Ошибка сохранения чанков: {str(e)}"
    
    def index_pending_documents(self, limit: Optional[int] = None) -> dict:
        """
        Индексировать все документы в статусе PENDING.
        
        Args:
            limit: Макс. кол-во документов
            
        Returns:
            Статистика индексации
        """
        pending_docs = self.document_repo.get_pending_documents(limit=limit)
        
        stats = {
            'total': len(pending_docs),
            'success': 0,
            'failed': 0,
            'chunks_created': 0,
            'errors': []
        }
        
        for doc in pending_docs:
            chunks_count, error = self.index_document(doc.id)
            
            if error:
                stats['failed'] += 1
                stats['errors'].append(f"Doc {doc.id}: {error}")
            else:
                stats['success'] += 1
                stats['chunks_created'] += chunks_count
        
        return stats
