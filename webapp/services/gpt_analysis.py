"""Сервис для работы с OpenAI GPT API."""
import os
import json
import requests
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from flask import current_app


class GPTAnalysisService:
    """Сервис для анализа текста через OpenAI GPT API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация сервиса.
        
        Args:
            api_key: API ключ OpenAI (если None, берётся из конфига)
        """
        self.api_key = api_key or self._get_api_key()
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-3.5-turbo"
        self.max_tokens = 150
        self.temperature = 0.7
    
    def _get_api_key(self) -> str:
        """Получить API ключ из конфигурации или переменных окружения."""
        try:
            return current_app.config.get('OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
        except Exception:
            return os.environ.get('OPENAI_API_KEY', '')
    
    def analyze_text(
        self,
        text: str,
        prompt: str,
        max_request_size: int = 4096
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Отправить текст на анализ в GPT.
        
        Args:
            text: Текст для анализа
            prompt: Промпт для GPT
            max_request_size: Максимальный размер запроса в символах
            
        Returns:
            tuple: (success, message, gpt_response)
        """
        try:
            # Проверяем наличие API ключа
            if not self.api_key:
                return False, 'API ключ OpenAI не настроен', None
            
            # Формируем полный запрос
            full_request = f"{prompt}\n\n{text}"
            
            # Проверяем размер запроса
            if len(full_request) > max_request_size:
                excess = len(full_request) - max_request_size
                return False, f'Размер запроса превышает лимит на {excess} символов', None
            
            # Формируем запрос к API
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": full_request
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            
            # Логируем отправку запроса
            try:
                current_app.logger.info(f'Отправка запроса к GPT API (размер: {len(full_request)} символов)')
            except Exception:
                pass
            
            # Отправляем запрос
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            # Логируем ответ
            try:
                current_app.logger.info(f'Ответ от GPT API: {response.status_code}')
            except Exception:
                pass
            
            # Проверяем статус ответа
            response.raise_for_status()
            
            # Парсим ответ
            result = response.json()
            choices = result.get("choices", [])
            
            if not choices:
                return False, 'GPT не вернул ответ', None
            
            gpt_response = choices[0]["message"]["content"]
            
            return True, 'Анализ выполнен успешно', gpt_response
            
        except requests.exceptions.Timeout:
            error_msg = 'Превышено время ожидания ответа от GPT API'
            try:
                current_app.logger.error(error_msg)
            except Exception:
                pass
            return False, error_msg, None
            
        except requests.exceptions.HTTPError as e:
            error_msg = f'Ошибка HTTP при обращении к GPT API: {e}'
            try:
                current_app.logger.error(error_msg)
            except Exception:
                pass
            return False, error_msg, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f'Ошибка сети при обращении к GPT API: {e}'
            try:
                current_app.logger.error(error_msg)
            except Exception:
                pass
            return False, error_msg, None
            
        except ValueError as e:
            error_msg = f'Ошибка обработки JSON ответа: {e}'
            try:
                current_app.logger.error(error_msg)
            except Exception:
                pass
            return False, error_msg, None
            
        except Exception as e:
            error_msg = f'Неизвестная ошибка при анализе: {e}'
            try:
                current_app.logger.exception(error_msg)
            except Exception:
                pass
            return False, error_msg, None
    
    def optimize_text(self, text: str, target_size: int) -> str:
        """
        Оптимизировать текст для уменьшения размера.
        
        Args:
            text: Исходный текст
            target_size: Целевой размер в символах
            
        Returns:
            Оптимизированный текст
        """
        if len(text) <= target_size:
            return text
        
        # Удаляем лишние пробелы и переносы строк
        lines = text.split('\n')
        optimized_lines = []
        
        for line in lines:
            # Удаляем лишние пробелы
            cleaned = ' '.join(line.split())
            if cleaned:
                optimized_lines.append(cleaned)
        
        optimized_text = '\n'.join(optimized_lines)
        
        # Если всё ещё слишком длинный, обрезаем
        if len(optimized_text) > target_size:
            optimized_text = optimized_text[:target_size]
        
        return optimized_text


class PromptManager:
    """Менеджер для работы с промптами."""
    
    def __init__(self, prompts_folder: str):
        """
        Инициализация менеджера.
        
        Args:
            prompts_folder: Папка для хранения промптов
        """
        self.prompts_folder = prompts_folder
        os.makedirs(self.prompts_folder, exist_ok=True)
        self.last_prompt_file = os.path.join(self.prompts_folder, '_last_prompt.txt')
    
    def save_prompt(self, prompt: str, filename: Optional[str] = None) -> Tuple[bool, str]:
        """
        Сохранить промпт в файл.
        
        Args:
            prompt: Текст промпта
            filename: Имя файла (если None, генерируется автоматически)
            
        Returns:
            tuple: (success, message)
        """
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'prompt_{timestamp}.txt'
            
            # Обеспечиваем расширение .txt
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            filepath = os.path.join(self.prompts_folder, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            # Сохраняем как последний использованный
            with open(self.last_prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            return True, f'Промпт сохранён: {filename}'
            
        except Exception as e:
            return False, f'Ошибка при сохранении промпта: {e}'
    
    def load_prompt(self, filename: str) -> Tuple[bool, str, Optional[str]]:
        """
        Загрузить промпт из файла.
        
        Args:
            filename: Имя файла
            
        Returns:
            tuple: (success, message, prompt_text)
        """
        try:
            filepath = os.path.join(self.prompts_folder, filename)
            
            if not os.path.exists(filepath):
                return False, f'Файл не найден: {filename}', None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                prompt = f.read()
            
            # Сохраняем как последний использованный
            with open(self.last_prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            return True, 'Промпт загружен', prompt
            
        except Exception as e:
            return False, f'Ошибка при загрузке промпта: {e}', None
    
    def get_last_prompt(self) -> str:
        """
        Получить последний использованный промпт.
        
        Returns:
            Текст промпта или промпт по умолчанию
        """
        try:
            if os.path.exists(self.last_prompt_file):
                with open(self.last_prompt_file, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception:
            pass
        
        # Промпт по умолчанию
        return "Проанализируй следующие документы и предоставь краткую сводку:"
    
    def list_prompts(self) -> List[str]:
        """
        Получить список сохранённых промптов.
        
        Returns:
            Список имён файлов
        """
        try:
            files = []
            for filename in os.listdir(self.prompts_folder):
                if filename.endswith('.txt') and not filename.startswith('_'):
                    files.append(filename)
            return sorted(files, reverse=True)
        except Exception:
            return []
