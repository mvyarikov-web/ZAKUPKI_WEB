"""
Централизованный менеджер для управления API ключами различных провайдеров.
Поддерживает хранение, валидацию и получение информации о доступных моделях.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Путь к файлу с API ключами (шифрованное хранение в продакшене!)
API_KEYS_FILE = Path(__file__).parent.parent / 'index' / 'api_keys.json'

# Конфигурация провайдеров
PROVIDERS = {
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'models_endpoint': '/models',
        'test_model': 'gpt-3.5-turbo',
        'key_prefix': 'sk-'
    },
    'deepseek': {
        'name': 'DeepSeek',
        'base_url': 'https://api.deepseek.com',
        'models_endpoint': '/models',
        'test_model': 'deepseek-chat',
        'key_prefix': 'sk-'
    }
}


class APIKeysManager:
    """Менеджер для управления API ключами"""
    
    def __init__(self):
        self.keys_file = API_KEYS_FILE
        self._ensure_keys_file()
    
    def _ensure_keys_file(self):
        """Создаёт файл с ключами, если его нет"""
        if not self.keys_file.exists():
            self.keys_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump({'providers': {}}, f, ensure_ascii=False, indent=2)
    
    def save_key(self, provider: str, api_key: str) -> Dict:
        """
        Сохраняет API ключ для провайдера
        
        Args:
            provider: Имя провайдера ('openai', 'deepseek')
            api_key: API ключ
            
        Returns:
            Dict с результатом операции
        """
        try:
            if provider not in PROVIDERS:
                return {
                    'success': False,
                    'error': f'Неизвестный провайдер: {provider}'
                }
            
            # Читаем текущие ключи
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Сохраняем ключ
            if 'providers' not in data:
                data['providers'] = {}
            
            data['providers'][provider] = {
                'api_key': api_key,
                'added_at': datetime.now().isoformat(),
                'last_validated': None,
                'status': 'not_validated'
            }
            
            # Записываем обратно
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"API ключ для {provider} успешно сохранён")
            
            return {
                'success': True,
                'message': f'Ключ для {PROVIDERS[provider]["name"]} сохранён'
            }
            
        except Exception as e:
            logger.error(f"Ошибка сохранения ключа для {provider}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_key(self, provider: str) -> Optional[str]:
        """
        Получает API ключ для провайдера
        
        Args:
            provider: Имя провайдера
            
        Returns:
            API ключ или None
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            provider_data = data.get('providers', {}).get(provider, {})
            return provider_data.get('api_key')
            
        except Exception as e:
            logger.error(f"Ошибка чтения ключа для {provider}: {e}")
            return None
    
    def delete_key(self, provider: str) -> Dict:
        """
        Удаляет API ключ провайдера
        
        Args:
            provider: Имя провайдера
            
        Returns:
            Dict с результатом операции
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if provider in data.get('providers', {}):
                del data['providers'][provider]
                
                with open(self.keys_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"API ключ для {provider} удалён")
                
                return {
                    'success': True,
                    'message': f'Ключ для {PROVIDERS[provider]["name"]} удалён'
                }
            else:
                return {
                    'success': False,
                    'error': f'Ключ для {provider} не найден'
                }
                
        except Exception as e:
            logger.error(f"Ошибка удаления ключа для {provider}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_keys(self) -> Dict:
        """
        Возвращает список всех сохранённых ключей (без самих ключей)
        
        Returns:
            Dict со списком провайдеров и их статусами
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            providers = data.get('providers', {})
            result = []
            
            for provider, info in providers.items():
                if provider in PROVIDERS:
                    result.append({
                        'provider': provider,
                        'name': PROVIDERS[provider]['name'],
                        'status': info.get('status', 'not_validated'),
                        'added_at': info.get('added_at'),
                        'last_validated': info.get('last_validated'),
                        'has_key': True,
                        'key_masked': self._mask_key(info.get('api_key', ''))
                    })
            
            # Добавляем провайдеров без ключей
            for provider, config in PROVIDERS.items():
                if provider not in providers:
                    result.append({
                        'provider': provider,
                        'name': config['name'],
                        'status': 'no_key',
                        'has_key': False,
                        'key_masked': ''
                    })
            
            return {
                'success': True,
                'providers': result
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения списка ключей: {e}")
            return {
                'success': False,
                'error': str(e),
                'providers': []
            }
    
    def validate_key(self, provider: str, api_key: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Проверяет валидность API ключа и получает список доступных моделей
        
        Args:
            provider: Имя провайдера
            api_key: API ключ (если None, берётся из сохранённых)
            
        Returns:
            Tuple (success, info_dict)
        """
        try:
            # Если ключ не передан, берём из сохранённых
            if api_key is None:
                api_key = self.get_key(provider)
            
            if not api_key:
                return False, {'error': 'API ключ не найден'}
            
            if provider not in PROVIDERS:
                return False, {'error': f'Неизвестный провайдер: {provider}'}
            
            config = PROVIDERS[provider]
            
            # Выполняем тестовый запрос
            if provider == 'openai':
                result = self._validate_openai(api_key, config)
            elif provider == 'deepseek':
                result = self._validate_deepseek(api_key, config)
            else:
                return False, {'error': f'Валидация для {provider} не реализована'}
            
            # Сохраняем результат валидации
            if result['success']:
                self._update_validation_status(provider, 'valid', result.get('models', []))
            else:
                self._update_validation_status(provider, 'invalid', [])
            
            return result['success'], result
            
        except Exception as e:
            logger.error(f"Ошибка валидации ключа для {provider}: {e}")
            return False, {'error': str(e)}
    
    def _validate_openai(self, api_key: str, config: Dict) -> Dict:
        """Валидация ключа OpenAI"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=api_key)
            
            # Простой тестовый запрос
            response = client.chat.completions.create(
                model=config['test_model'],
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            
            # Получаем список моделей
            models_response = client.models.list()
            available_models = [m.id for m in models_response.data if 'gpt' in m.id.lower()]
            
            return {
                'success': True,
                'message': 'Ключ OpenAI валиден',
                'models': available_models,
                'test_response': response.choices[0].message.content
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка OpenAI API: {str(e)}',
                'models': []
            }
    
    def _validate_deepseek(self, api_key: str, config: Dict) -> Dict:
        """Валидация ключа DeepSeek"""
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=api_key,
                base_url=config['base_url']
            )
            
            # Простой тестовый запрос
            response = client.chat.completions.create(
                model=config['test_model'],
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            
            # DeepSeek поддерживает две модели
            available_models = ['deepseek-chat', 'deepseek-reasoner']
            
            return {
                'success': True,
                'message': 'Ключ DeepSeek валиден',
                'models': available_models,
                'test_response': response.choices[0].message.content
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка DeepSeek API: {str(e)}',
                'models': []
            }
    
    def _update_validation_status(self, provider: str, status: str, models: List[str]):
        """Обновляет статус валидации в файле"""
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if provider in data.get('providers', {}):
                data['providers'][provider]['status'] = status
                data['providers'][provider]['last_validated'] = datetime.now().isoformat()
                data['providers'][provider]['available_models'] = models
                
                with open(self.keys_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            logger.error(f"Ошибка обновления статуса валидации: {e}")
    
    @staticmethod
    def _mask_key(key: str) -> str:
        """Маскирует API ключ для отображения"""
        if not key or len(key) < 8:
            return '***'
        return f"{key[:4]}...{key[-4:]}"
    
    def get_key_for_model(self, model_id: str) -> Optional[str]:
        """
        Получает API ключ для указанной модели
        
        Args:
            model_id: ID модели (например, 'gpt-4o' или 'deepseek-chat')
            
        Returns:
            API ключ или None
        """
        if model_id.startswith('deepseek-'):
            return self.get_key('deepseek')
        else:
            return self.get_key('openai')


# Глобальный экземпляр менеджера
_manager = None

def get_api_keys_manager() -> APIKeysManager:
    """Получить глобальный экземпляр менеджера ключей"""
    global _manager
    if _manager is None:
        _manager = APIKeysManager()
    return _manager
