"""Сервис для чанкования текста документов.

Разбивает длинные документы на фрагменты оптимального размера для RAG.
"""
import re
import hashlib
from typing import List, Dict, Any, Optional

# tiktoken может отсутствовать; используем graceful degrade
try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover
    tiktoken = None  # fallback маркер


class TextChunker:
    """Чанкование текста с учётом семантических границ."""
    
    def __init__(
        self,
        chunk_size_tokens: int = 2000,
        overlap_sentences: int = 3,
        encoding_name: str = "cl100k_base"
    ):
        """
        Инициализация чанкера.
        
        Args:
            chunk_size_tokens: Максимальный размер чанка в токенах
            overlap_sentences: Количество предложений для overlap
            encoding_name: Название токенизатора tiktoken
        """
        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_sentences = overlap_sentences
        try:
            self.encoding = tiktoken.get_encoding(encoding_name) if tiktoken else None
        except Exception:
            # Фолбэк на примерный подсчёт
            self.encoding = None
    
    def count_tokens(self, text: str) -> int:
        """
        Подсчитать количество токенов в тексте.
        
        Args:
            text: Текст для подсчёта
            
        Returns:
            Количество токенов
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception:
                pass
        
        # Примерная оценка: ~4 символа на токен для английского, ~3 для русского
        return len(text) // 3
    
    def split_into_sentences(self, text: str) -> List[str]:
        """
        Разбить текст на предложения.
        
        Args:
            text: Входной текст
            
        Returns:
            Список предложений
        """
        # Регулярное выражение для разбиения на предложения
        # Учитывает точки, вопросительные и восклицательные знаки
        # Не разбивает на сокращениях (т.е., и т.д., г., км.)
        pattern = r'(?<!\w\.\w.)(?<![A-ZА-Я][a-zа-я]\.)(?<=\.|\?|\!)\s+'
        sentences = re.split(pattern, text)
        
        # Убираем пустые строки
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def create_chunks(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Создать чанки из текста.
        
        Args:
            text: Входной текст
            metadata: Метаданные для всех чанков
            
        Returns:
            Список словарей с чанками:
                - content: текст чанка
                - token_count: количество токенов
                - chunk_index: индекс чанка
                - content_hash: хеш содержимого
                - metadata: метаданные
        """
        if not text or not text.strip():
            return []
        
        # Разбиваем на предложения
        sentences = self.split_into_sentences(text)
        
        if not sentences:
            return []
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        
        for i, sentence in enumerate(sentences):
            sentence_tokens = self.count_tokens(sentence)
            
            # Если предложение само больше лимита, разбиваем его
            if sentence_tokens > self.chunk_size_tokens:
                # Сохраняем текущий чанк, если есть
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunks.append(self._create_chunk_dict(
                        chunk_text,
                        chunk_index,
                        metadata
                    ))
                    chunk_index += 1
                    current_chunk = []
                    current_tokens = 0
                
                # Разбиваем длинное предложение по словам
                words = sentence.split()
                word_chunk = []
                word_tokens = 0
                
                for word in words:
                    word_token_count = self.count_tokens(word + ' ')
                    if word_tokens + word_token_count > self.chunk_size_tokens and word_chunk:
                        # Сохраняем чанк из слов
                        chunk_text = ' '.join(word_chunk)
                        chunks.append(self._create_chunk_dict(
                            chunk_text,
                            chunk_index,
                            metadata
                        ))
                        chunk_index += 1
                        word_chunk = []
                        word_tokens = 0
                    
                    word_chunk.append(word)
                    word_tokens += word_token_count
                
                # Остаток
                if word_chunk:
                    chunk_text = ' '.join(word_chunk)
                    current_chunk = [chunk_text]
                    current_tokens = word_tokens
                
                continue
            
            # Проверяем, помещается ли предложение в текущий чанк
            if current_tokens + sentence_tokens > self.chunk_size_tokens:
                # Сохраняем текущий чанк
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunks.append(self._create_chunk_dict(
                        chunk_text,
                        chunk_index,
                        metadata
                    ))
                    chunk_index += 1
                
                # Создаём overlap из последних N предложений
                overlap_start = max(0, len(current_chunk) - self.overlap_sentences)
                current_chunk = current_chunk[overlap_start:]
                current_tokens = sum(self.count_tokens(s) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
        
        # Сохраняем последний чанк
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append(self._create_chunk_dict(
                chunk_text,
                chunk_index,
                metadata
            ))
        
        return chunks
    
    def _create_chunk_dict(
        self,
        content: str,
        chunk_index: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Создать словарь с данными чанка."""
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        token_count = self.count_tokens(content)
        
        return {
            'content': content,
            'chunk_index': chunk_index,
            'token_count': token_count,
            'content_hash': content_hash,
            'metadata': metadata or {}
        }
    
    def clean_text(self, text: str) -> str:
        """
        Очистить текст от мусора перед чанкованием.
        
        Args:
            text: Исходный текст
            
        Returns:
            Очищенный текст
        """
        if not text:
            return ""
        
        # Убираем повторяющиеся пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # Убираем дефисы переноса
        text = re.sub(r'-\s*\n\s*', '', text)
        
        # Нормализуем переносы строк
        text = re.sub(r'\n+', '\n', text)
        
        # Убираем пробелы в начале и конце
        text = text.strip()
        
        return text
    
    def extract_sections(self, text: str) -> Dict[str, str]:
        """
        Извлечь разделы из документа (эвристический подход).
        
        Args:
            text: Текст документа
            
        Returns:
            Словарь {название_раздела: текст_раздела}
        """
        sections = {}
        
        # Ищем заголовки разделов (простая эвристика)
        # Заголовки обычно короткие, в верхнем регистре или с цифрами
        section_pattern = r'^(?:\d+\.?\s+)?([А-ЯЁA-Z][А-ЯЁA-Z\s]{3,50})$'
        
        lines = text.split('\n')
        current_section = 'Основной текст'
        current_content = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Проверяем, является ли строка заголовком
            match = re.match(section_pattern, line_stripped)
            if match and len(line_stripped) < 100:
                # Сохраняем предыдущий раздел
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                
                # Начинаем новый раздел
                current_section = match.group(1).strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Сохраняем последний раздел
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections


def chunk_document(
    text: str,
    file_path: str,
    chunk_size_tokens: int = 2000,
    overlap_sentences: int = 3
) -> List[Dict[str, Any]]:
    """
    Удобная функция для чанкования документа.
    
    Args:
        text: Текст документа
        file_path: Путь к файлу (для метаданных)
        chunk_size_tokens: Размер чанка в токенах
        overlap_sentences: Overlap в предложениях
        
    Returns:
        Список чанков с метаданными
    """
    chunker = TextChunker(chunk_size_tokens, overlap_sentences)
    
    # Очищаем текст
    cleaned_text = chunker.clean_text(text)
    
    # Извлекаем разделы (опционально)
    sections = chunker.extract_sections(cleaned_text)
    
    # Если есть разделы, чанкуем каждый отдельно
    all_chunks = []
    if len(sections) > 1:
        for section_name, section_text in sections.items():
            section_chunks = chunker.create_chunks(
                section_text,
                metadata={
                    'file_path': file_path,
                    'section': section_name
                }
            )
            all_chunks.extend(section_chunks)
    else:
        # Чанкуем весь текст целиком
        all_chunks = chunker.create_chunks(
            cleaned_text,
            metadata={'file_path': file_path}
        )
    
    # Переиндексируем чанки
    for i, chunk in enumerate(all_chunks):
        chunk['chunk_index'] = i
    
    return all_chunks
