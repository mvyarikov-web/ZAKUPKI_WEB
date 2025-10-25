"""Тесты для RAG-модуля: чанкование, эмбеддинги, индексация."""
import pytest
import os
from webapp.services.chunking import TextChunker, chunk_document
from webapp.services.embeddings import EmbeddingsService


class TestChunking:
    """Тесты чанкования текста."""
    
    def test_chunker_initialization(self):
        """Тест инициализации чанкера."""
        chunker = TextChunker(chunk_size_tokens=1000, overlap_sentences=2)
        
        assert chunker.chunk_size_tokens == 1000
        assert chunker.overlap_sentences == 2
    
    def test_count_tokens(self):
        """Тест подсчёта токенов."""
        chunker = TextChunker()
        
        text = "Это тестовый текст для проверки подсчёта токенов."
        token_count = chunker.count_tokens(text)
        
        # Примерная проверка (должно быть > 0)
        assert token_count > 0
        assert token_count < 50  # Короткий текст
    
    def test_split_into_sentences(self):
        """Тест разбиения на предложения."""
        chunker = TextChunker()
        
        text = "Первое предложение. Второе предложение! Третье предложение?"
        sentences = chunker.split_into_sentences(text)
        
        assert len(sentences) == 3
        assert "Первое предложение" in sentences[0]
        assert "Второе предложение" in sentences[1]
        assert "Третье предложение" in sentences[2]
    
    def test_create_chunks_simple(self):
        """Тест создания чанков из короткого текста."""
        chunker = TextChunker(chunk_size_tokens=100, overlap_sentences=1)
        
        text = "Первое предложение. Второе предложение. Третье предложение."
        chunks = chunker.create_chunks(text)
        
        assert len(chunks) >= 1
        assert chunks[0]['chunk_index'] == 0
        assert 'content' in chunks[0]
        assert 'token_count' in chunks[0]
        assert 'content_hash' in chunks[0]
    
    def test_create_chunks_long_text(self):
        """Тест создания чанков из длинного текста."""
        chunker = TextChunker(chunk_size_tokens=50, overlap_sentences=1)
        
        # Генерируем длинный текст
        sentences = [f"Предложение номер {i}." for i in range(20)]
        text = " ".join(sentences)
        
        chunks = chunker.create_chunks(text)
        
        # Должно быть несколько чанков
        assert len(chunks) > 1
        
        # Проверяем, что индексы правильные
        for i, chunk in enumerate(chunks):
            assert chunk['chunk_index'] == i
    
    def test_clean_text(self):
        """Тест очистки текста."""
        chunker = TextChunker()
        
        text = "Текст  с   лишними    пробелами\n\n\nи переносами"
        cleaned = chunker.clean_text(text)
        
        # Проверяем, что лишние пробелы убраны
        assert "  " not in cleaned
        assert "\n\n\n" not in cleaned
    
    def test_chunk_document(self):
        """Тест функции chunk_document."""
        text = """
        Техническое задание на поставку климатического оборудования.
        
        Требуется поставить кондиционеры мощностью 3.5 кВт в количестве 10 штук.
        Монтаж и пусконаладка входят в стоимость.
        """
        
        chunks = chunk_document(text, file_path="test.txt", chunk_size_tokens=100)
        
        assert len(chunks) >= 1
        assert all('content' in c for c in chunks)
        assert all('chunk_index' in c for c in chunks)


class TestEmbeddings:
    """Тесты сервиса эмбеддингов."""
    
    def test_embeddings_service_initialization(self):
        """Тест инициализации сервиса."""
        # Без API ключа (для теста)
        service = EmbeddingsService(api_key="test-key")
        
        assert service.api_key == "test-key"
        assert service.model == "text-embedding-3-small"
    
    def test_get_dimension(self):
        """Тест получения размерности векторов."""
        service = EmbeddingsService(api_key="test-key")
        
        dimension = service.get_dimension()
        
        assert dimension == 1536  # Для text-embedding-3-small
    
    @pytest.mark.skipif(
        not os.environ.get('OPENAI_API_KEY'),
        reason="OpenAI API ключ не настроен"
    )
    def test_get_embedding_real_api(self):
        """Тест получения реального эмбеддинга (требует API ключ)."""
        service = EmbeddingsService()
        
        text = "Тестовый текст для векторизации"
        embedding = service.get_embedding(text)
        
        assert embedding is not None
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)


class TestRAGIntegration:
    """Интеграционные тесты RAG."""
    
    @pytest.mark.skipif(
        not os.environ.get('DATABASE_URL'),
        reason="PostgreSQL не настроен"
    )
    def test_database_connection(self):
        """Тест подключения к БД."""
        from webapp.models.rag_models import RAGDatabase
        
        db_url = os.environ.get('DATABASE_URL')
        db = RAGDatabase(db_url)
        
        # Пробуем создать схему
        try:
            db.initialize_schema()
            
            # Получаем статистику
            stats = db.get_stats()
            
            assert 'documents' in stats
            assert 'chunks' in stats
        except Exception as e:
            pytest.skip(f"База данных недоступна: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
