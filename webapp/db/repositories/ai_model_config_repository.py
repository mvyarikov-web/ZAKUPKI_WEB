"""
Репозиторий для работы с конфигурацией AI моделей.
Замена legacy файла models.json.
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from webapp.db.models import AIModelConfig
from webapp.db.repositories.base_repository import BaseRepository


class AIModelConfigRepository(BaseRepository[AIModelConfig]):
    """Репозиторий для работы с конфигурацией AI моделей."""
    
    def __init__(self, session: Session):
        super().__init__(session, AIModelConfig)
    
    def get_by_model_id(self, model_id: str) -> Optional[AIModelConfig]:
        """Получить конфигурацию модели по model_id."""
        return self.session.query(AIModelConfig).filter(
            AIModelConfig.model_id == model_id
        ).first()
    
    def get_enabled_models(self) -> List[AIModelConfig]:
        """Получить все включённые модели."""
        return self.session.query(AIModelConfig).filter(
            AIModelConfig.is_enabled == True
        ).order_by(AIModelConfig.display_name).all()
    
    def get_models_by_provider(self, provider: str, enabled_only: bool = True) -> List[AIModelConfig]:
        """Получить модели по провайдеру."""
        query = self.session.query(AIModelConfig).filter(
            AIModelConfig.provider == provider
        )
        if enabled_only:
            query = query.filter(AIModelConfig.is_enabled == True)
        return query.order_by(AIModelConfig.display_name).all()
    
    def get_default_model(self) -> Optional[AIModelConfig]:
        """Получить модель по умолчанию."""
        return self.session.query(AIModelConfig).filter(
            AIModelConfig.is_default == True,
            AIModelConfig.is_enabled == True
        ).first()
    
    def set_default_model(self, model_id: str) -> bool:
        """Установить модель по умолчанию."""
        try:
            # Снимаем флаг default со всех моделей
            self.session.query(AIModelConfig).update({AIModelConfig.is_default: False})
            
            # Устанавливаем флаг для выбранной модели
            model = self.get_by_model_id(model_id)
            if not model:
                return False
            
            model.is_default = True
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False
    
    def create_or_update(self, model_id: str, data: Dict[str, Any]) -> AIModelConfig:
        """Создать или обновить конфигурацию модели."""
        existing = self.get_by_model_id(model_id)
        
        if existing:
            # Обновляем существующую
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            self.session.commit()
            return existing
        else:
            # Создаём новую
            data['model_id'] = model_id
            model = AIModelConfig(**data)
            self.session.add(model)
            self.session.commit()
            return model
    
    def to_legacy_format(self, models: List[AIModelConfig]) -> Dict[str, Any]:
        """
        Конвертировать список моделей в формат legacy models.json.
        Для обратной совместимости со старым кодом.
        """
        models_list = []
        default_model_id = None
        
        for model in models:
            model_dict = {
                'model_id': model.model_id,
                'display_name': model.display_name,
                'provider': model.provider,
                'context_window_tokens': model.context_window_tokens,
                'max_output_tokens': model.max_output_tokens,
                'price_input_per_1m': float(model.price_input_per_1m or 0) / 100.0,  # центы → доллары
                'price_output_per_1m': float(model.price_output_per_1m or 0) / 100.0,
                'supports_system_role': model.supports_system_role,
                'supports_streaming': model.supports_streaming,
                'supports_function_calling': model.supports_function_calling,
                'enabled': model.is_enabled,
                'timeout': model.timeout_seconds,
            }
            
            if model.pricing_model == 'per_request':
                model_dict['pricing_model'] = 'per_request'
                model_dict['price_per_1000_requests'] = float(model.price_per_1000_requests or 0) / 100.0
            
            if model.config_json:
                model_dict.update(model.config_json)
            
            models_list.append(model_dict)
            
            if model.is_default:
                default_model_id = model.model_id
        
        # Если нет default, берём первую включённую
        if not default_model_id and models_list:
            default_model_id = models_list[0]['model_id']
        
        return {
            'models': models_list,
            'default_model': default_model_id
        }
    
    def from_legacy_format(self, legacy_data: Dict[str, Any]) -> None:
        """
        Импортировать данные из legacy формата models.json в БД.
        Используется для миграции.
        """
        models_list = legacy_data.get('models', [])
        default_model_id = legacy_data.get('default_model')
        
        for model_data in models_list:
            # Конвертируем цены из долларов в центы
            price_input = float(model_data.get('price_input_per_1m', 0) or 0)
            price_output = float(model_data.get('price_output_per_1m', 0) or 0)
            price_per_request = float(model_data.get('price_per_1000_requests', 0) or 0)
            
            data = {
                'display_name': model_data.get('display_name', model_data['model_id']),
                'provider': model_data.get('provider', 'openai'),
                'context_window_tokens': model_data.get('context_window_tokens', 4096),
                'max_output_tokens': model_data.get('max_output_tokens'),
                'price_input_per_1m': int(price_input * 100),  # доллары → центы
                'price_output_per_1m': int(price_output * 100),
                'price_per_1000_requests': int(price_per_request * 100) if price_per_request > 0 else None,
                'pricing_model': model_data.get('pricing_model', 'per_token'),
                'supports_system_role': model_data.get('supports_system_role', True),
                'supports_streaming': model_data.get('supports_streaming', True),
                'supports_function_calling': model_data.get('supports_function_calling', False),
                'is_enabled': model_data.get('enabled', True),
                'is_default': model_data['model_id'] == default_model_id,
                'timeout_seconds': model_data.get('timeout', 60),
                'config_json': {k: v for k, v in model_data.items() 
                               if k not in ['model_id', 'display_name', 'provider', 
                                           'context_window_tokens', 'max_output_tokens',
                                           'price_input_per_1m', 'price_output_per_1m',
                                           'price_per_1000_requests', 'pricing_model',
                                           'supports_system_role', 'supports_streaming',
                                           'supports_function_calling', 'enabled', 'timeout']}
            }
            
            self.create_or_update(model_data['model_id'], data)
