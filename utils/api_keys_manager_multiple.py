"""
Расширенный менеджер для управления множественными API ключами различных провайдеров.
Поддерживает хранение нескольких ключей для одного провайдера с выбором основного.
"""
import json
import os
import uuid
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


class APIKeysManagerMultiple:
    """Менеджер для управления множественными API ключами"""
    
    def __init__(self):
        self.keys_file = API_KEYS_FILE
        self._ensure_keys_file()
        self._migrate_old_format()
    
    def _ensure_keys_file(self):
        """Создаёт файл с ключами, если его нет"""
        if not self.keys_file.exists():
            self.keys_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump({'providers': {}}, f, ensure_ascii=False, indent=2)
    
    def _migrate_old_format(self):
        """Мигрирует старый формат (один ключ) в новый (массив ключей)"""
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            providers = data.get('providers', {})
            migrated = False
            
            for provider, value in list(providers.items()):
                # Если это старый формат (api_key напрямую в providers[provider])
                if isinstance(value, dict) and 'api_key' in value and not isinstance(value.get('keys'), list):
                    old_key = value['api_key']
                    old_status = value.get('status', 'not_validated')
                    old_models = value.get('available_models', [])
                    old_added_at = value.get('added_at')
                    
                    # Создаём новый формат
                    providers[provider] = {
                        'keys': [
                            {
                                'key_id': str(uuid.uuid4()),
                                'api_key': old_key,
                                'is_primary': True,
                                'status': old_status,
                                'models_count': len(old_models),
                                'added_at': old_added_at or datetime.now().isoformat(),
                                'last_validated': value.get('last_validated')
                            }
                        ]
                    }
                    migrated = True
                    logger.info(f"Мигрирован ключ для {provider} в новый формат")
            
            if migrated:
                with open(self.keys_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info("Миграция в новый формат завершена")
                
        except Exception as e:
            logger.error(f"Ошибка миграции формата: {e}")
    
    def add_key(self, provider: str, api_key: str, models_count: int = 0, available_models: List[str] = None) -> Dict:
        """
        Добавляет новый API ключ для провайдера
        
        Args:
            provider: Имя провайдера ('openai', 'deepseek')
            api_key: API ключ
            models_count: Количество доступных моделей
            
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
            
            if 'providers' not in data:
                data['providers'] = {}
            
            if provider not in data['providers']:
                data['providers'][provider] = {'keys': []}
            
            # Проверяем, не существует ли уже такой ключ
            existing_keys = data['providers'][provider].get('keys', [])
            for key_data in existing_keys:
                if key_data['api_key'] == api_key:
                    return {
                        'success': False,
                        'error': 'Такой ключ уже добавлен'
                    }
            
            # Если это первый ключ, делаем его основным
            is_primary = len(existing_keys) == 0
            
            # Добавляем новый ключ
            new_key = {
                'key_id': str(uuid.uuid4()),
                'api_key': api_key,
                'is_primary': is_primary,
                'status': 'valid',  # Предполагаем, что ключ уже провалидирован
                'models_count': models_count,
                'available_models': available_models or [],
                'added_at': datetime.now().isoformat(),
                'last_validated': datetime.now().isoformat()
            }
            
            existing_keys.append(new_key)
            data['providers'][provider]['keys'] = existing_keys
            
            # Записываем обратно
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"API ключ для {provider} успешно добавлен (ID: {new_key['key_id']})")
            
            return {
                'success': True,
                'message': f'Ключ для {PROVIDERS[provider]["name"]} добавлен',
                'key_id': new_key['key_id']
            }
            
        except Exception as e:
            logger.error(f"Ошибка добавления ключа для {provider}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_key(self, provider: str) -> Optional[str]:
        """
        Получает основной API ключ для провайдера
        
        Args:
            provider: Имя провайдера
            
        Returns:
            API ключ или None
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            provider_data = data.get('providers', {}).get(provider, {})
            keys = provider_data.get('keys', [])
            
            # Ищем основной ключ
            for key_data in keys:
                if key_data.get('is_primary'):
                    return key_data['api_key']
            
            # Если основного нет, возвращаем первый валидный
            for key_data in keys:
                if key_data.get('status') == 'valid':
                    return key_data['api_key']
            
            # Если валидных нет, возвращаем первый
            if keys:
                return keys[0]['api_key']
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения ключа для {provider}: {e}")
            return None
    
    def set_primary_key(self, provider: str, key_id: str) -> Dict:
        """
        Устанавливает ключ как основной для провайдера
        
        Args:
            provider: Имя провайдера
            key_id: ID ключа
            
        Returns:
            Dict с результатом операции
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            provider_data = data.get('providers', {}).get(provider, {})
            keys = provider_data.get('keys', [])
            
            key_found = False
            for key_data in keys:
                if key_data['key_id'] == key_id:
                    key_data['is_primary'] = True
                    key_found = True
                else:
                    key_data['is_primary'] = False
            
            if not key_found:
                return {
                    'success': False,
                    'error': 'Ключ не найден'
                }
            
            # Записываем обратно
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Основной ключ для {provider} установлен: {key_id}")
            
            return {
                'success': True,
                'message': 'Основной ключ обновлён'
            }
            
        except Exception as e:
            logger.error(f"Ошибка установки основного ключа: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_key(self, provider: str, key_id: str) -> Dict:
        """
        Удаляет ключ
        
        Args:
            provider: Имя провайдера
            key_id: ID ключа
            
        Returns:
            Dict с результатом операции
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            provider_data = data.get('providers', {}).get(provider, {})
            keys = provider_data.get('keys', [])
            
            # Находим и удаляем ключ
            new_keys = [k for k in keys if k['key_id'] != key_id]
            
            if len(new_keys) == len(keys):
                return {
                    'success': False,
                    'error': 'Ключ не найден'
                }
            
            # Если удалили основной ключ и остались другие, делаем первый основным
            if new_keys:
                has_primary = any(k.get('is_primary') for k in new_keys)
                if not has_primary:
                    new_keys[0]['is_primary'] = True
            
            data['providers'][provider]['keys'] = new_keys
            
            # Записываем обратно
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Ключ {key_id} для {provider} удалён")
            
            return {
                'success': True,
                'message': 'Ключ удалён'
            }
            
        except Exception as e:
            logger.error(f"Ошибка удаления ключа: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_all_keys(self) -> Dict:
        """
        Возвращает список всех ключей
        
        Returns:
            Dict со списком ключей
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            providers = data.get('providers', {})
            all_keys = []
            
            for provider, provider_data in providers.items():
                keys = provider_data.get('keys', [])
                for key_data in keys:
                    all_keys.append({
                        'provider': provider,
                        'key_id': key_data['key_id'],
                        'api_key': key_data['api_key'],
                        'is_primary': key_data.get('is_primary', False),
                        'status': key_data.get('status', 'not_validated'),
                        'models_count': key_data.get('models_count', 0),
                        'available_models': key_data.get('available_models', []),
                        'added_at': key_data.get('added_at'),
                        'last_validated': key_data.get('last_validated')
                    })
            
            return {
                'success': True,
                'keys': all_keys
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения списка ключей: {e}")
            return {
                'success': False,
                'error': str(e),
                'keys': []
            }
    
    def update_key_info(self, provider: str, key_id: str, status: str, models_count: int, available_models: List[str]) -> Dict:
        """
        Обновляет информацию о ключе (статус, модели)
        
        Args:
            provider: Имя провайдера
            key_id: ID ключа
            status: Новый статус
            models_count: Количество моделей
            available_models: Список доступных моделей
            
        Returns:
            Dict с результатом операции
        """
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            provider_data = data.get('providers', {}).get(provider, {})
            keys = provider_data.get('keys', [])
            
            key_found = False
            for key_data in keys:
                if key_data['key_id'] == key_id:
                    key_data['status'] = status
                    key_data['models_count'] = models_count
                    key_data['available_models'] = available_models
                    key_data['last_validated'] = datetime.now().isoformat()
                    key_found = True
                    break
            
            if not key_found:
                return {
                    'success': False,
                    'error': 'Ключ не найден'
                }
            
            # Записываем обратно
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Информация о ключе {key_id} обновлена")
            
            return {
                'success': True,
                'message': 'Информация обновлена'
            }
            
        except Exception as e:
            logger.error(f"Ошибка обновления информации о ключе: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_key(self, provider: str, api_key: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Проверяет валидность API ключа и получает список доступных моделей
        
        Args:
            provider: Имя провайдера
            api_key: API ключ (если None, берётся основной из сохранённых)
            
        Returns:
            Tuple (success, info_dict)
        """
        try:
            # Если ключ не передан, берём основной из сохранённых
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
            
            return result['success'], result
            
        except Exception as e:
            logger.error(f"Ошибка валидации ключа для {provider}: {e}")
            return False, {'error': str(e)}
    
    def _validate_openai(self, api_key: str, config: Dict) -> Dict:
        """Валидация ключа OpenAI с получением аналитики"""
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
            
            # Аналитика из заголовков ответа
            analytics = {
                'test_tokens_used': response.usage.total_tokens if response.usage else None,
                'test_prompt_tokens': response.usage.prompt_tokens if response.usage else None,
                'test_completion_tokens': response.usage.completion_tokens if response.usage else None,
            }
            
            # Пытаемся определить тип ключа по префиксу
            key_type = 'unknown'
            if api_key.startswith('sk-proj-'):
                key_type = 'project'
            elif api_key.startswith('sk-'):
                key_type = 'user'
            
            analytics['key_type'] = key_type
            analytics['models_count'] = len(available_models)
            
            return {
                'success': True,
                'message': 'Ключ OpenAI валиден',
                'models': available_models,
                'test_response': response.choices[0].message.content,
                'analytics': analytics
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # Детализируем ошибки аутентификации
            if '401' in error_msg or 'Incorrect API key' in error_msg:
                error_msg = f'Неверный API ключ. Проверьте правильность ключа в настройках OpenAI.'
            elif '429' in error_msg:
                error_msg = 'Превышен лимит запросов. Попробуйте позже или проверьте квоты.'
            elif '403' in error_msg:
                error_msg = 'Доступ запрещён. Проверьте права API ключа.'
            
            return {
                'success': False,
                'error': f'Ошибка OpenAI API: {error_msg}',
                'models': [],
                'analytics': None
            }
    
    def _validate_deepseek(self, api_key: str, config: Dict) -> Dict:
        """Валидация ключа DeepSeek с получением аналитики"""
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
            
            # Аналитика из заголовков ответа
            analytics = {
                'test_tokens_used': response.usage.total_tokens if response.usage else None,
                'test_prompt_tokens': response.usage.prompt_tokens if response.usage else None,
                'test_completion_tokens': response.usage.completion_tokens if response.usage else None,
            }
            
            # DeepSeek ключи начинаются с sk-
            analytics['key_type'] = 'standard' if api_key.startswith('sk-') else 'unknown'
            analytics['models_count'] = len(available_models)
            
            return {
                'success': True,
                'message': 'Ключ DeepSeek валиден',
                'models': available_models,
                'test_response': response.choices[0].message.content if response.choices[0].message.content else '(пустой ответ)',
                'analytics': analytics
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # Детализируем ошибки аутентификации
            if '401' in error_msg or 'invalid' in error_msg.lower():
                error_msg = f'Неверный API ключ DeepSeek. Проверьте ключ на https://platform.deepseek.com/api_keys'
            elif '429' in error_msg:
                error_msg = 'Превышен лимит запросов DeepSeek. Проверьте баланс и квоты.'
            elif '403' in error_msg:
                error_msg = 'Доступ запрещён. Проверьте статус аккаунта DeepSeek.'
            
            return {
                'success': False,
                'error': f'Ошибка DeepSeek API: {error_msg}',
                'models': [],
                'analytics': None
            }


# Глобальный экземпляр менеджера
_manager_instance = None

def get_api_keys_manager_multiple():
    """Получить глобальный экземпляр менеджера ключей"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = APIKeysManagerMultiple()
    return _manager_instance
