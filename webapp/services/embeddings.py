"""Сервис для работы с эмбеддингами OpenAI."""
import os
from typing import List, Optional
import openai
from flask import current_app


class EmbeddingsService:
    """Сервис для генерации векторных представлений текста."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small"
    ):
        """
        Инициализация сервиса.
        
        Args:
            api_key: API ключ OpenAI (если None, берётся из конфига/env)
            model: Модель эмбеддингов
        """
        self.api_key = api_key or self._get_api_key()
        self.model = model
        
        # Настраиваем клиент OpenAI
        if self.api_key:
            openai.api_key = self.api_key
    
    def _get_api_key(self) -> str:
        """Получить API ключ из конфигурации или переменных окружения."""
        # Сначала из окружения
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if api_key:
            return api_key
        
        # Затем из конфига Flask
        try:
            return current_app.config.get('OPENAI_API_KEY', '')
        except Exception:
            return ''
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Получить векторное представление для текста.
        
        Args:
            text: Текст для векторизации
            
        Returns:
            Вектор эмбеддинга или None при ошибке
        """
        if not self.api_key:
            raise ValueError("OpenAI API ключ не настроен")
        
        if not text or not text.strip():
            return None
        
        try:
            # Используем новый API клиент OpenAI
            client = openai.OpenAI(api_key=self.api_key)
            
            response = client.embeddings.create(
                model=self.model,
                input=text.strip()
            )
            
            if response and response.data:
                return response.data[0].embedding
            
            return None
            
        except Exception as e:
            try:
                current_app.logger.error(f'Ошибка получения эмбеддинга: {e}')
            except Exception:
                pass
            return None
    
    def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[Optional[List[float]]]:
        """
        Получить эмбеддинги для батча текстов.
        
        Args:
            texts: Список текстов
            batch_size: Размер батча для API
            
        Returns:
            Список векторов (None для ошибок)
        """
        if not self.api_key:
            raise ValueError("OpenAI API ключ не настроен")
        
        if not texts:
            return []
        
        # Фильтруем пустые тексты
        filtered_texts = [(i, t.strip()) for i, t in enumerate(texts) if t and t.strip()]
        
        if not filtered_texts:
            return [None] * len(texts)
        
        # Результирующий массив
        results = [None] * len(texts)
        
        try:
            client = openai.OpenAI(api_key=self.api_key)
            
            # Обрабатываем батчами
            for batch_start in range(0, len(filtered_texts), batch_size):
                batch_end = min(batch_start + batch_size, len(filtered_texts))
                batch = filtered_texts[batch_start:batch_end]
                
                # Извлекаем только тексты для API
                batch_texts = [t[1] for t in batch]
                
                try:
                    response = client.embeddings.create(
                        model=self.model,
                        input=batch_texts
                    )
                    
                    if response and response.data:
                        # Распределяем результаты по исходным индексам
                        for j, embedding_obj in enumerate(response.data):
                            original_index = batch[j][0]
                            results[original_index] = embedding_obj.embedding
                
                except Exception as e:
                    try:
                        current_app.logger.error(f'Ошибка батч-эмбеддинга: {e}')
                    except Exception:
                        pass
                    # Пропускаем этот батч, оставляя None
            
            return results
            
        except Exception as e:
            try:
                current_app.logger.error(f'Ошибка батч-обработки эмбеддингов: {e}')
            except Exception:
                pass
            return [None] * len(texts)
    
    def get_dimension(self) -> int:
        """Получить размерность векторов для модели."""
        # Размерности для разных моделей
        dimensions = {
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
            'text-embedding-ada-002': 1536,
        }
        return dimensions.get(self.model, 1536)


def get_embeddings_service(
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> EmbeddingsService:
    """
    Фабрика для создания сервиса эмбеддингов.
    
    Args:
        api_key: API ключ (опционально)
        model: Модель эмбеддингов (опционально)
        
    Returns:
        Экземпляр EmbeddingsService
    """
    if model is None:
        try:
            model = current_app.config.get('RAG_EMBEDDING_MODEL', 'text-embedding-3-small')
        except Exception:
            model = 'text-embedding-3-small'
    
    return EmbeddingsService(api_key=api_key, model=model)
