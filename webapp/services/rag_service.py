"""Основной сервис RAG для анализа документов.

Объединяет индексацию, векторный поиск и генерацию структурированных ответов.
"""
import os
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from flask import current_app
import openai

from webapp.models.rag_models import RAGDatabase
from webapp.services.chunking import chunk_document, TextChunker
from webapp.services.embeddings import get_embeddings_service
from document_processor.core import DocumentProcessor
from utils.api_keys_manager_multiple import get_api_keys_manager_multiple


class RAGService:
    """Сервис для RAG-анализа документов."""
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """
        Инициализация RAG-сервиса.
        
        Args:
            database_url: URL подключения к PostgreSQL
            api_key: API ключ OpenAI
        """
        self.database_url = database_url or self._get_database_url()
        self.api_key = api_key or self._get_api_key()
        
        # Инициализация компонентов
        try:
            self.db = RAGDatabase(self.database_url)
            self.db_available = True
        except Exception as e:
            try:
                current_app.logger.warning(f'PostgreSQL недоступен: {e}')
            except Exception:
                pass
            self.db = None
            self.db_available = False
        
        self.embeddings_service = get_embeddings_service(api_key=self.api_key)
        self.doc_processor = DocumentProcessor()
    
    def _get_database_url(self) -> str:
        """Получить URL базы данных из конфигурации."""
        try:
            return current_app.config.get('DATABASE_URL', '')
        except Exception:
            return os.environ.get('DATABASE_URL', '')
    
    def _get_api_key(self) -> str:
        """Получить API ключ OpenAI."""
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if api_key:
            return api_key
        
        try:
            return current_app.config.get('OPENAI_API_KEY', '')
        except Exception:
            return ''
    
    def initialize_database(self):
        """Инициализировать схему базы данных."""
        if not self.db_available:
            raise RuntimeError("База данных недоступна")
        
        self.db.initialize_schema()
    
    def index_document(
        self,
        file_path: str,
        upload_folder: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Индексировать документ для RAG.
        
        Args:
            file_path: Относительный путь к файлу
            upload_folder: Базовая папка с файлами
            
        Returns:
            Tuple (success, message, stats)
        """
        if not self.db_available:
            return False, "База данных недоступна", None
        
        if not self.api_key:
            return False, "OpenAI API ключ не настроен", None
        
        try:
            # Формируем полный путь
            full_path = os.path.join(upload_folder, file_path)
            
            if not os.path.exists(full_path):
                return False, f"Файл не найден: {file_path}", None
            
            # Извлекаем текст
            text = self.doc_processor.extract_text(full_path)
            
            if not text or not text.strip():
                return False, f"Не удалось извлечь текст из файла", None
            
            # Вычисляем хеш файла
            file_hash = self._calculate_file_hash(full_path)
            file_size = os.path.getsize(full_path)
            file_name = os.path.basename(file_path)
            
            # Проверяем, не индексирован ли уже документ с таким же хешем
            existing_doc = self.db.get_document_by_path(file_path)
            if existing_doc and existing_doc.get('file_hash') == file_hash:
                return True, f"Документ уже проиндексирован", {
                    'document_id': existing_doc['id'],
                    'chunks_count': 0,
                    'skipped': True
                }
            
            # Добавляем документ в базу
            doc_id = self.db.add_document(
                file_path=file_path,
                file_name=file_name,
                file_hash=file_hash,
                file_size=file_size,
                metadata={'source': 'upload'}
            )
            
            # Чанкуем текст
            chunk_size = self._get_config('RAG_CHUNK_SIZE', 2000)
            overlap = self._get_config('RAG_CHUNK_OVERLAP', 3)
            
            chunks = chunk_document(
                text,
                file_path=file_path,
                chunk_size_tokens=chunk_size,
                overlap_sentences=overlap
            )
            
            if not chunks:
                return False, "Не удалось создать чанки из текста", None
            
            # Получаем эмбеддинги для всех чанков
            chunk_texts = [c['content'] for c in chunks]
            embeddings = self.embeddings_service.get_embeddings_batch(chunk_texts)
            
            # Подготавливаем данные для вставки
            chunks_with_embeddings = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                if embedding is None:
                    continue  # Пропускаем чанки без эмбеддингов
                
                chunks_with_embeddings.append({
                    'document_id': doc_id,
                    'chunk_index': i,
                    'content': chunk['content'],
                    'content_hash': chunk['content_hash'],
                    'embedding': embedding,
                    'token_count': chunk['token_count'],
                    'metadata': chunk.get('metadata', {})
                })
            
            if not chunks_with_embeddings:
                return False, "Не удалось получить эмбеддинги для чанков", None
            
            # Сохраняем чанки в базу
            self.db.add_chunks(chunks_with_embeddings)
            
            return True, f"Документ проиндексирован успешно", {
                'document_id': doc_id,
                'chunks_count': len(chunks_with_embeddings),
                'skipped': False
            }
        
        except Exception as e:
            try:
                current_app.logger.exception(f'Ошибка индексации документа {file_path}: {e}')
            except Exception:
                pass
            return False, f"Ошибка индексации: {str(e)}", None
    
    def search_and_analyze(
        self,
        query: str,
        file_paths: List[str],
        model: str = "gpt-4o-mini",
        top_k: int = 5,
        max_output_tokens: int = 600,
        temperature: float = 0.3,
        upload_folder: Optional[str] = None,
        search_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Выполнить RAG-анализ документов.
        
        Args:
            query: Запрос/промпт пользователя
            file_paths: Список путей к файлам для анализа
            model: Модель GPT для генерации
            top_k: Количество чанков для контекста
            max_output_tokens: Максимум токенов в ответе
            temperature: Температура генерации
            upload_folder: Папка с файлами (для фолбэка)
            search_params: Параметры поиска для Perplexity (если используется режим поиска)
            
        Returns:
            Tuple (success, message, result_dict)
        """
        if not self.db_available:
            return False, "База данных недоступна", None
        
        if not self.api_key:
            return False, "OpenAI API ключ не настроен", None
        
        try:
            # Получаем эмбеддинг запроса
            try:
                query_embedding = self.embeddings_service.get_embedding(query)
            except Exception as emb_err:
                current_app.logger.exception(f'Ошибка при получении эмбеддинга запроса: {emb_err}')
                return False, f"Ошибка эмбеддинга: {str(emb_err)}", None
            
            if not query_embedding:
                return False, "Не удалось получить эмбеддинг запроса. Проверьте API-ключ и подключение к OpenAI.", None
            
            # Получаем ID документов для фильтрации
            document_ids = []
            try:
                for file_path in file_paths:
                    doc = self.db.get_document_by_path(file_path)
                    if doc:
                        document_ids.append(doc['id'])
            except Exception as db_err:
                # Ошибка подключения к БД - помечаем как недоступную
                current_app.logger.warning(f'Ошибка подключения к БД: {db_err}')
                self.db_available = False
                return False, "База данных недоступна", None
            
            if not document_ids:
                return False, "Документы не проиндексированы", None
            
            # Ищем релевантные чанки
            min_similarity = self._get_config('RAG_MIN_SIMILARITY', 0.7)
            
            try:
                relevant_chunks = self.db.search_similar_chunks(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    document_ids=document_ids
                )
            except Exception as db_err:
                # Ошибка при поиске - помечаем БД как недоступную
                current_app.logger.warning(f'Ошибка поиска в БД: {db_err}')
                self.db_available = False
                return False, "База данных недоступна", None
            
            if not relevant_chunks:
                return False, "Не найдено релевантных фрагментов", None
            
            # Формируем контекст из чанков
            context = self._build_context(relevant_chunks)
            
            # Формируем промпт для структурированного ответа
            system_prompt = self._get_system_prompt()
            user_prompt = self._build_user_prompt(query, context)
            
            # Подсчитываем токены
            chunker = TextChunker()
            input_tokens = chunker.count_tokens(system_prompt + user_prompt)
            
            # Отправляем запрос к модели (OpenAI или DeepSeek)
            client = self._get_client_for_model(model)
            
            # Формируем параметры запроса
            request_params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"}
            }
            
            # При включённом поиске не ограничиваем max_tokens, иначе устанавливаем лимит
            if not search_params:
                request_params["max_tokens"] = max_output_tokens
            # else: max_tokens не устанавливаем, чтобы не обрезать ответ при поиске
            
            # ВАРИАНТ B: Явное управление поиском через disable_search
            # Если переданы параметры поиска (для Perplexity models с поиском)
            if search_params:
                # Режим С ПОИСКОМ: disable_search НЕ устанавливаем (по умолчанию False)
                # Добавляем параметры поиска к запросу
                if search_params.get('max_results'):
                    request_params['max_results'] = search_params['max_results']
                if search_params.get('search_domain_filter'):
                    request_params['search_domain_filter'] = search_params['search_domain_filter']
                if search_params.get('search_recency_filter'):
                    request_params['search_recency_filter'] = search_params['search_recency_filter']
                if search_params.get('search_after_date'):
                    request_params['search_after_date'] = search_params['search_after_date']
                if search_params.get('search_before_date'):
                    request_params['search_before_date'] = search_params['search_before_date']
                if search_params.get('country'):
                    request_params['country'] = search_params['country']
                if search_params.get('max_tokens_per_page'):
                    request_params['max_tokens_per_page'] = search_params['max_tokens_per_page']
                
                current_app.logger.info(f'🌐 Режим С ПОИСКОМ: параметры = {search_params}')
            else:
                # Режим БЕЗ ПОИСКА: явно отключаем поиск для Perplexity моделей
                if 'sonar' in model.lower() or 'perplexity' in model.lower():
                    request_params['disable_search'] = True
                    current_app.logger.info(f'🚫 Режим БЕЗ ПОИСКА: disable_search = True для модели {model}')
            
            response = client.chat.completions.create(**request_params)
            
            # Проверяем факт использования поиска в ответе
            search_used = False
            if hasattr(response, 'search_results') and response.search_results:
                search_used = True
                current_app.logger.info(f'✅ Поиск БЫЛ использован: найдено {len(response.search_results)} результатов')
            else:
                current_app.logger.info(f'📝 Поиск НЕ использован (только знания модели)')
            
            if not response or not response.choices:
                return False, "Не получен ответ от GPT", None
            
            # Парсим ответ
            response_text = response.choices[0].message.content
            
            try:
                structured_response = json.loads(response_text)
            except json.JSONDecodeError:
                return False, "Ошибка парсинга ответа GPT", None
            
            # Подсчёт токенов
            usage = response.usage
            actual_input_tokens = usage.prompt_tokens if usage else input_tokens
            actual_output_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else (input_tokens + actual_output_tokens)
            
            # Постобработка результата
            processed_result = self._postprocess_result(
                structured_response,
                relevant_chunks
            )
            
            # Определяем, был ли использован поиск (проверяем наличие результатов поиска)
            search_was_used = hasattr(response, 'search_results') and response.search_results is not None and len(response.search_results) > 0
            
            # Формируем название модели с суффиксом "+ Search" если поиск использован
            model_display_name = model
            if search_was_used:
                model_display_name = f"{model} + Search"
            
            # Формируем итоговый результат
            result = {
                'summary': processed_result.get('summary', []),
                'equipment': processed_result.get('equipment', []),
                'installation': processed_result.get('installation', {}),
                'usage': {
                    'input_tokens': actual_input_tokens,
                    'output_tokens': actual_output_tokens,
                    'total_tokens': total_tokens
                },
                'model': model_display_name,
                'search_used': search_was_used,  # Флаг фактического использования поиска
                'chunks_used': len(relevant_chunks),
                'sources': [
                    {
                        'file_name': c['file_name'],
                        'similarity': c['similarity']
                    }
                    for c in relevant_chunks
                ]
            }
            
            return True, "Анализ выполнен успешно", result
        
        except Exception as e:
            try:
                current_app.logger.exception(f'Ошибка RAG-анализа: {e}')
            except Exception:
                pass
            return False, f"Ошибка анализа: {str(e)}", None
    
    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Сформировать контекст из чанков."""
        context_parts = []
        
        for i, chunk in enumerate(chunks):
            file_name = chunk.get('file_name', 'Unknown')
            content = chunk.get('content', '')
            similarity = chunk.get('similarity', 0)
            
            context_parts.append(
                f"[Источник {i+1}: {file_name}, релевантность: {similarity:.2f}]\n{content}\n"
            )
        
        return "\n".join(context_parts)
    
    def _get_system_prompt(self) -> str:
        """Получить системный промпт для структурированного ответа."""
        return """Ты — эксперт по анализу документов закупок климатической техники.
Твоя задача — проанализировать предоставленные фрагменты документов и дать структурированный ответ в формате JSON.

Формат ответа:
{
  "summary": ["краткий пункт 1", "краткий пункт 2", ... до 10 пунктов],
  "equipment": [
    {
      "name": "название оборудования",
      "model": "модель (если указана)",
      "characteristics": {
        "мощность": "значение с единицами",
        "производительность": "значение",
        ...
      },
      "qty": число или null,
      "unit": "шт/комплект/т и т.п." или null,
      "evidence": ["короткая цитата 1", "короткая цитата 2"]
    }
  ],
  "installation": {
    "verdict": true|false|"unknown",
    "evidence": ["цитата с упоминанием монтажа", "цитата о ПНР", ...]
  }
}

Инструкции:
1. summary — краткая выжимка ключевых моментов закупки (до 10 пунктов).
2. equipment — список всего оборудования с характеристиками и цитатами-подтверждениями.
3. installation.verdict:
   - true, если явно упоминается монтаж, установка, ПНР, шеф-монтаж, СМР, пусконаладка
   - false, если явно указано "без монтажа" или "только поставка"
   - "unknown", если информация неоднозначна
4. evidence — короткие цитаты (1-2 предложения), подтверждающие выводы.

Отвечай ТОЛЬКО в формате JSON, без дополнительного текста."""
    
    def _build_user_prompt(self, query: str, context: str) -> str:
        """Сформировать пользовательский промпт."""
        return f"""Запрос пользователя: {query}

Фрагменты документов:
{context}

Проанализируй документы и предоставь структурированный ответ в формате JSON согласно инструкциям."""
    
    def _postprocess_result(
        self,
        response: Dict[str, Any],
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Постобработка результата: дедупликация, агрегация.
        
        Args:
            response: Ответ от GPT
            chunks: Использованные чанки
            
        Returns:
            Обработанный результат
        """
        # Дедупликация оборудования
        equipment_dict = {}
        for eq in response.get('equipment', []):
            key = (eq.get('name', '').lower().strip(), eq.get('model', '').lower().strip())
            
            if key in equipment_dict:
                # Объединяем характеристики
                existing = equipment_dict[key]
                existing_chars = existing.get('characteristics', {})
                new_chars = eq.get('characteristics', {})
                
                # Добавляем новые характеристики, не перезаписывая существующие
                for k, v in new_chars.items():
                    if k not in existing_chars:
                        existing_chars[k] = v
                
                existing['characteristics'] = existing_chars
                
                # Объединяем evidence
                existing_evidence = set(existing.get('evidence', []))
                new_evidence = set(eq.get('evidence', []))
                existing['evidence'] = list(existing_evidence | new_evidence)
            else:
                equipment_dict[key] = eq
        
        deduplicated_equipment = list(equipment_dict.values())
        
        # Агрегация вердикта по монтажу
        installation = response.get('installation', {})
        verdict = installation.get('verdict', 'unknown')
        
        # Если хоть где-то уверенное "да", то true
        # Если везде "нет", то false
        # Иначе unknown
        
        result = {
            'summary': response.get('summary', [])[:10],  # Ограничиваем 10 пунктами
            'equipment': deduplicated_equipment,
            'installation': installation
        }
        
        return result
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Вычислить хеш файла."""
        hasher = hashlib.md5()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def _get_config(self, key: str, default: Any) -> Any:
        """Получить значение из конфигурации."""
        try:
            return current_app.config.get(key, default)
        except Exception:
            return default
    
    def get_database_stats(self) -> Optional[Dict[str, int]]:
        """Получить статистику по базе данных."""
        if not self.db_available:
            return None
        
        try:
            return self.db.get_stats()
        except Exception:
            return None
    
    def _get_client_for_model(self, model: str) -> openai.OpenAI:
        """
        Получить OpenAI-совместимый клиент для указанной модели.
        
        Args:
            model: ID модели (например, 'gpt-4o-mini' или 'deepseek-chat')
            
        Returns:
            Настроенный клиент OpenAI
        """
        api_keys_mgr = get_api_keys_manager_multiple()
        
        # Проверяем, является ли это моделью DeepSeek (только конкретные ID)
        deepseek_models = ['deepseek-chat', 'deepseek-reasoner']
        if model in deepseek_models:
            # Получаем API ключ DeepSeek из менеджера
            deepseek_key = api_keys_mgr.get_key('deepseek')
            if not deepseek_key:
                # Fallback на переменные окружения
                deepseek_key = os.environ.get('DEEPSEEK_API_KEY')
                if not deepseek_key:
                    # Последний fallback на OpenAI ключ
                    try:
                        current_app.logger.warning('DEEPSEEK_API_KEY не найден, используется OPENAI_API_KEY')
                    except Exception:
                        pass
                    deepseek_key = self.api_key
            
            # Создаём клиент для DeepSeek API
            return openai.OpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com"
            )
        # Perplexity (семейство sonar: sonar, sonar-pro, sonar-reasoning, sonar-reasoning-pro, sonar-deep-research)
        pplx_prefixes = ('sonar',)
        if any(model.startswith(p) for p in pplx_prefixes):
            pplx_key = api_keys_mgr.get_key('perplexity') or os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY') or self.api_key
            return openai.OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")
        
        # Для моделей OpenAI получаем ключ из менеджера
        openai_key = api_keys_mgr.get_key('openai') or self.api_key
        return openai.OpenAI(api_key=openai_key)


def get_rag_service(
    database_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> RAGService:
    """
    Фабрика для создания RAG-сервиса.
    
    Args:
        database_url: URL базы данных
        api_key: API ключ OpenAI
        
    Returns:
        Экземпляр RAGService
    """
    return RAGService(database_url=database_url, api_key=api_key)
