"""
Сервис для работы с конфигурацией AI моделей.
Замена legacy models.json с автоматическим переключением между БД и файлом.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
from flask import current_app

logger = logging.getLogger(__name__)


class AIModelConfigService:
    """Сервис для работы с конфигурацией AI моделей."""
    
    def __init__(self):
        """Инициализация сервиса."""
        self.use_database = self._should_use_database()
    
    def _should_use_database(self) -> bool:
        """Определить, использовать ли БД."""
        try:
            if current_app:
                return current_app.config.get('use_database', False)
        except Exception:
            pass
        return os.environ.get('USE_DATABASE', 'false').lower() in ('true', '1', 'yes', 'on')
    
    def _get_legacy_path(self) -> str:
        """Получить путь к legacy файлу models.json."""
        try:
            root = current_app.root_path if current_app else os.getcwd()
        except Exception:
            root = os.getcwd()
        
        try:
            override = current_app.config.get("RAG_MODELS_FILE") if current_app else None
        except Exception:
            override = None
        
        if override:
            return override
        return os.path.join(root, "index", "models.json")
    
    def _load_from_file(self) -> Dict[str, Any]:
        """Загрузить конфигурацию из legacy файла."""
        path = self._get_legacy_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Миграция старого формата
                if isinstance(data, list):
                    data = {
                        "models": data,
                        "default_model": data[0]["model_id"] if data else None,
                    }
                
                # Приводим ключи цены к единому формату
                for m in data.get("models", []):
                    if "price_input_per_1M" in m and "price_input_per_1m" not in m:
                        m["price_input_per_1m"] = m.pop("price_input_per_1M")
                    if "price_output_per_1M" in m and "price_output_per_1m" not in m:
                        m["price_output_per_1m"] = m.pop("price_output_per_1M")
                
                return data
        except Exception as e:
            logger.exception(f"Ошибка чтения {path}: {e}")
        
        # Дефолтная конфигурация
        return {
            "models": [
                {
                    "model_id": "gpt-4o-mini",
                    "display_name": "GPT-4o Mini",
                    "provider": "openai",
                    "context_window_tokens": 128000,
                    "price_input_per_1m": 0.15,
                    "price_output_per_1m": 0.60,
                    "enabled": True,
                    "supports_system_role": True,
                }
            ],
            "default_model": "gpt-4o-mini",
        }
    
    def _save_to_file(self, config: Dict[str, Any]) -> None:
        """Сохранить конфигурацию в legacy файл."""
        path = self._get_legacy_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def _load_from_db(self) -> Dict[str, Any]:
        """Загрузить конфигурацию из БД."""
        from webapp.db import get_db
        from webapp.db.repositories.ai_model_config_repository import AIModelConfigRepository
        
        db = next(get_db())
        try:
            repo = AIModelConfigRepository(db)
            models = repo.get_enabled_models()
            return repo.to_legacy_format(models)
        finally:
            db.close()
    
    def _save_to_db(self, config: Dict[str, Any]) -> None:
        """Сохранить конфигурацию в БД."""
        from webapp.db import get_db
        from webapp.db.repositories.ai_model_config_repository import AIModelConfigRepository
        
        db = next(get_db())
        try:
            repo = AIModelConfigRepository(db)
            repo.from_legacy_format(config)
        finally:
            db.close()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Загрузить конфигурацию моделей.
        
        Returns:
            Dict с полями:
            - models: List[Dict] - список моделей
            - default_model: str - ID модели по умолчанию
        """
        try:
            if self.use_database:
                return self._load_from_db()
            else:
                return self._load_from_file()
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации моделей: {e}")
            # Возвращаем дефолтную конфигурацию
            return self._load_from_file()
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """
        Сохранить конфигурацию моделей.
        
        Args:
            config: Словарь с полями models и default_model
        """
        try:
            if self.use_database:
                self._save_to_db(config)
                # Также сохраняем в файл для обратной совместимости
                self._save_to_file(config)
            else:
                self._save_to_file(config)
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации моделей: {e}")
            raise
    
    def get_model_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Получить конфигурацию модели по ID."""
        config = self.load_config()
        for model in config.get('models', []):
            if model.get('model_id') == model_id:
                return model
        return None
    
    def get_default_model(self) -> Optional[Dict[str, Any]]:
        """Получить модель по умолчанию."""
        config = self.load_config()
        default_id = config.get('default_model')
        if default_id:
            return self.get_model_by_id(default_id)
        
        # Если нет default, возвращаем первую включённую
        models = config.get('models', [])
        enabled = [m for m in models if m.get('enabled', True)]
        return enabled[0] if enabled else None
    
    def set_default_model(self, model_id: str) -> bool:
        """Установить модель по умолчанию."""
        try:
            config = self.load_config()
            
            # Проверяем, что модель существует
            model_exists = any(m.get('model_id') == model_id for m in config.get('models', []))
            if not model_exists:
                return False
            
            config['default_model'] = model_id
            self.save_config(config)
            return True
        except Exception as e:
            logger.error(f"Ошибка установки default модели: {e}")
            return False
    
    def add_models(self, models: List[Dict[str, Any]]) -> None:
        """
        Добавить модели в конфигурацию.
        Если модель с таким model_id уже существует, обновляет её.
        """
        config = self.load_config()
        existing_ids = {m.get('model_id') for m in config.get('models', [])}
        
        for new_model in models:
            model_id = new_model.get('model_id')
            if not model_id:
                continue
            
            if model_id in existing_ids:
                # Обновляем существующую модель
                for i, m in enumerate(config['models']):
                    if m.get('model_id') == model_id:
                        config['models'][i].update(new_model)
                        break
            else:
                # Добавляем новую модель
                config['models'].append(new_model)
                existing_ids.add(model_id)
        
        self.save_config(config)
    
    def migrate_from_file_to_db(self) -> bool:
        """
        Мигрировать данные из файла в БД.
        Используется для одноразовой миграции.
        """
        try:
            # Загружаем из файла
            file_config = self._load_from_file()
            
            # Сохраняем в БД
            self._save_to_db(file_config)
            
            logger.info(f"Миграция моделей в БД завершена: {len(file_config.get('models', []))} моделей")
            return True
        except Exception as e:
            logger.error(f"Ошибка миграции моделей в БД: {e}")
            return False


# Singleton instance
_service_instance: Optional[AIModelConfigService] = None


def get_ai_model_config_service() -> AIModelConfigService:
    """Получить singleton instance сервиса."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AIModelConfigService()
    return _service_instance
