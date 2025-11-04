#!/usr/bin/env python3
"""
Скрипт миграции данных из файлового хранилища в PostgreSQL
Increment 013 - Шаг 15

Функции:
- Миграция документов из uploads/ → documents.blob
- Миграция API ключей из index/api_keys.json → api_keys (с шифрованием Fernet)
- Миграция моделей из index/models.json → ai_model_configs
- Создание дефолтного пользователя (admin@localhost)
- Поддержка --dry-run для проверки без изменений
- Логирование прогресса и ошибок

Зависимости: DATABASE_URL, API_ENCRYPTION_KEY в environment
"""

import os
import sys
import json
import hashlib
import mimetypes
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
import argparse

# Настраиваем путь для импорта webapp модулей
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet
import bcrypt

from webapp.db.models import (
    Base, User, Document, APIKey, UserModel
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Статистика миграции"""
    def __init__(self):
        self.users_created = 0
        self.documents_migrated = 0
        self.documents_skipped = 0
        self.documents_errors = 0
        self.api_keys_migrated = 0
        self.api_keys_errors = 0
        self.models_migrated = 0
        self.models_errors = 0
    
    def print_summary(self):
        """Вывести итоговую статистику"""
        logger.info("=" * 60)
        logger.info("ИТОГИ МИГРАЦИИ:")
        logger.info("-" * 60)
        logger.info(f"Пользователи созданы: {self.users_created}")
        logger.info(f"Документы мигрированы: {self.documents_migrated}")
        logger.info(f"Документы пропущены (дубликаты): {self.documents_skipped}")
        logger.info(f"Документы с ошибками: {self.documents_errors}")
        logger.info(f"API ключи мигрированы: {self.api_keys_migrated}")
        logger.info(f"API ключи с ошибками: {self.api_keys_errors}")
        logger.info(f"Модели мигрированы: {self.models_migrated}")
        logger.info(f"Модели с ошибками: {self.models_errors}")
        logger.info("=" * 60)


class FilesToDBMigrator:
    """Главный класс миграции"""
    
    def __init__(self, db_url: str, encryption_key: str, dry_run: bool = False):
        """
        Args:
            db_url: PostgreSQL connection string
            encryption_key: Fernet key для шифрования API ключей
            dry_run: Если True, не применять изменения
        """
        self.db_url = db_url
        self.cipher = Fernet(encryption_key.encode())
        self.dry_run = dry_run
        self.stats = MigrationStats()
        
        # Настраиваем БД
        self.engine = create_engine(db_url, echo=False)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        
        logger.info(f"Режим: {'DRY-RUN (без изменений)' if dry_run else 'РЕАЛЬНАЯ МИГРАЦИЯ'}")
        logger.info(f"База данных: {db_url.split('@')[-1]}")  # Скрываем пароль
    
    def create_default_user(self) -> Optional[User]:
        """
        Создать дефолтного пользователя для однопользовательской системы
        
        Returns:
            User объект или None (dry-run)
        """
        logger.info("Проверка наличия пользователей в БД...")
        
        existing_user = self.session.query(User).filter_by(
            email='admin@localhost'
        ).first()
        
        if existing_user:
            logger.info(f"Найден существующий пользователь: admin@localhost (ID={existing_user.id})")
            return existing_user
        
        if self.dry_run:
            logger.info("[DRY-RUN] Будет создан пользователь: admin@localhost")
            return None
        
        # Создаём нового пользователя
        password_hash = bcrypt.hashpw('changeme'.encode(), bcrypt.gensalt()).decode()
        
        user = User(
            email='admin@localhost',
            password_hash=password_hash,
            role='admin',
            created_at=datetime.now(timezone.utc)
        )
        
        self.session.add(user)
        self.session.commit()
        
        self.stats.users_created += 1
        logger.info(f"✅ Создан пользователь: {user.email} (ID={user.id})")
        logger.warning(f"⚠️  Дефолтный пароль: 'changeme' - ОБЯЗАТЕЛЬНО смените после миграции!")
        
        return user
    
    def migrate_documents(self, user: Optional[User], uploads_dir: Path) -> None:
        """
        Мигрировать документы из uploads/ в documents.blob
        
        Args:
            user: Владелец документов (None в dry-run)
            uploads_dir: Путь к папке uploads/
        """
        logger.info("=" * 60)
        logger.info("МИГРАЦИЯ ДОКУМЕНТОВ")
        logger.info("=" * 60)
        
        if not uploads_dir.exists():
            logger.warning(f"Директория {uploads_dir} не найдена, пропускаем документы")
            return
        
        # Собираем все файлы рекурсивно
        files = [f for f in uploads_dir.rglob('*') if f.is_file()]
        logger.info(f"Найдено файлов: {len(files)}")
        
        for file_path in files:
            try:
                # Читаем файл
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                # Вычисляем SHA256
                sha256 = hashlib.sha256(content).hexdigest()
                
                # Проверяем дубликаты (только если есть user)
                if user:
                    existing = self.session.query(Document).filter_by(
                        owner_id=user.id,
                        sha256=sha256
                    ).first()
                    
                    if existing:
                        logger.info(f"SKIP (дубликат): {file_path.name} → уже есть ID={existing.id}")
                        self.stats.documents_skipped += 1
                        continue
                
                # Определяем content_type
                content_type, _ = mimetypes.guess_type(str(file_path))
                if not content_type:
                    content_type = 'application/octet-stream'
                
                # Получаем дату модификации
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                
                if self.dry_run:
                    logger.info(
                        f"[DRY-RUN] {file_path.name} "
                        f"({len(content)} bytes, {content_type}, SHA256={sha256[:8]}...)"
                    )
                    self.stats.documents_migrated += 1
                    continue
                
                # Создаём запись в БД
                doc = Document(
                    owner_id=user.id,
                    original_filename=file_path.name,
                    content_type=content_type,
                    size_bytes=len(content),
                    sha256=sha256,
                    blob=content,  # Храним прямо в БД (для больших файлов можно использовать storage_url)
                    status='new',
                    uploaded_at=mtime
                )
                
                self.session.add(doc)
                self.session.commit()
                
                logger.info(
                    f"✅ {file_path.name} → document_id={doc.id} "
                    f"({doc.size_bytes} bytes, SHA256={doc.sha256[:8]}...)"
                )
                self.stats.documents_migrated += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка при миграции {file_path}: {e}")
                self.stats.documents_errors += 1
                if not self.dry_run:
                    self.session.rollback()
    
    def migrate_api_keys(self, user: Optional[User], api_keys_file: Path) -> None:
        """
        Мигрировать API ключи из index/api_keys.json
        
        Args:
            user: Владелец ключей (None в dry-run)
            api_keys_file: Путь к JSON файлу с ключами
        """
        logger.info("=" * 60)
        logger.info("МИГРАЦИЯ API КЛЮЧЕЙ")
        logger.info("=" * 60)
        
        if not api_keys_file.exists():
            logger.warning(f"Файл {api_keys_file} не найден, пропускаем API ключи")
            return
        
        try:
            with open(api_keys_file, 'r', encoding='utf-8') as f:
                keys_data = json.load(f)
            
            logger.info(f"Найдено провайдеров: {len(keys_data)}")
            
            for provider, keys_list in keys_data.items():
                if not isinstance(keys_list, list):
                    logger.warning(f"Неверный формат для провайдера {provider}, пропускаем")
                    continue
                
                for idx, key_info in enumerate(keys_list):
                    try:
                        # Извлекаем данные
                        plaintext_key = key_info.get('key', '')
                        if not plaintext_key:
                            logger.warning(f"Пустой ключ для {provider}[{idx}], пропускаем")
                            continue
                        
                        # Шифруем ключ
                        ciphertext = self.cipher.encrypt(plaintext_key.encode()).decode()
                        
                        display_name = key_info.get('name', f'{provider} key #{idx+1}')
                        is_shared = key_info.get('is_shared', False)
                        
                        if self.dry_run:
                            logger.info(
                                f"[DRY-RUN] {provider}: {display_name} "
                                f"(shared={is_shared}, key={plaintext_key[:6]}...)"
                            )
                            self.stats.api_keys_migrated += 1
                            continue
                        
                        # Создаём запись (APIKey не имеет display_name, только provider)
                        api_key = APIKey(
                            user_id=user.id,
                            provider=provider,
                            key_ciphertext=ciphertext,
                            is_shared=is_shared,
                            created_at=datetime.now(timezone.utc)
                        )
                        
                        self.session.add(api_key)
                        self.session.commit()
                        
                        logger.info(
                            f"✅ {provider}: {display_name} → api_key_id={api_key.id} "
                            f"(encrypted, shared={is_shared})"
                        )
                        self.stats.api_keys_migrated += 1
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка при миграции ключа {provider}[{idx}]: {e}")
                        self.stats.api_keys_errors += 1
                        if not self.dry_run:
                            self.session.rollback()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при чтении {api_keys_file}: {e}")
    
    def migrate_models(self, user: Optional[User], models_file: Path) -> None:
        """
        Мигрировать модели из index/models.json
        
        Args:
            user: Владелец моделей (None в dry-run)
            models_file: Путь к JSON файлу с моделями
        """
        logger.info("=" * 60)
        logger.info("МИГРАЦИЯ МОДЕЛЕЙ")
        logger.info("=" * 60)
        
        if not models_file.exists():
            logger.warning(f"Файл {models_file} не найден, пропускаем модели")
            return
        
        try:
            with open(models_file, 'r', encoding='utf-8') as f:
                models_data = json.load(f)
            
            if not isinstance(models_data, list):
                logger.error("Неверный формат models.json (ожидается массив)")
                return
            
            logger.info(f"Найдено моделей: {len(models_data)}")
            
            for model_info in models_data:
                try:
                    model_id = model_info.get('id', '')
                    if not model_id:
                        logger.warning("Модель без ID, пропускаем")
                        continue
                    
                    if self.dry_run:
                        logger.info(
                            f"[DRY-RUN] {model_id}: {model_info.get('name', 'N/A')} "
                            f"(provider={model_info.get('provider', 'unknown')})"
                        )
                        self.stats.models_migrated += 1
                        continue
                    
                    # Проверяем дубликат
                    existing = self.session.query(UserModel).filter_by(
                        user_id=user.id,
                        model_id=model_id
                    ).first()
                    
                    if existing:
                        logger.info(f"SKIP: модель {model_id} уже существует (ID={existing.id})")
                        continue
                    
                    # Создаём запись (UserModel использует pricing JSON)
                    pricing_data = {
                        'input_price_per_1k': model_info.get('input_price', 0.0),
                        'output_price_per_1k': model_info.get('output_price', 0.0),
                        'context_window': model_info.get('context_window', 4096)
                    }
                    
                    model = UserModel(
                        user_id=user.id,
                        model_id=model_id,
                        display_name=model_info.get('name', model_id),
                        pricing=pricing_data,
                        is_active=model_info.get('is_active', True),
                        created_at=datetime.now(timezone.utc)
                    )
                    
                    self.session.add(model)
                    self.session.commit()
                    
                    logger.info(
                        f"✅ {model_id} → model_config_id={model.id} "
                        f"(provider={model.provider}, active={model.is_active})"
                    )
                    self.stats.models_migrated += 1
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при миграции модели: {e}")
                    self.stats.models_errors += 1
                    if not self.dry_run:
                        self.session.rollback()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при чтении {models_file}: {e}")
    
    def run(self) -> MigrationStats:
        """
        Запустить полную миграцию
        
        Returns:
            Статистика миграции
        """
        try:
            # Определяем пути
            base_dir = Path(__file__).resolve().parent.parent
            uploads_dir = base_dir / 'uploads'
            index_dir = base_dir / 'index'
            api_keys_file = index_dir / 'api_keys.json'
            models_file = index_dir / 'models.json'
            
            logger.info(f"Рабочая директория: {base_dir}")
            
            # Создаём пользователя
            user = self.create_default_user()
            
            # Миграция документов
            self.migrate_documents(user, uploads_dir)
            
            # Миграция API ключей
            self.migrate_api_keys(user, api_keys_file)
            
            # Миграция моделей
            self.migrate_models(user, models_file)
            
            # Итоги
            self.stats.print_summary()
            
            if self.dry_run:
                logger.info("✅ DRY-RUN завершён. Для реальной миграции запустите без --dry-run")
            else:
                logger.info("✅ МИГРАЦИЯ ЗАВЕРШЕНА!")
            
            return self.stats
            
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            if not self.dry_run:
                self.session.rollback()
            raise
        finally:
            self.session.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Миграция данных из файлов в PostgreSQL (Increment 013)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Проверка без изменений
  python scripts/migrate_files_to_db.py --dry-run
  
  # Реальная миграция
  python scripts/migrate_files_to_db.py
  
  # С указанием переменных напрямую
  DATABASE_URL=postgresql://user:pass@localhost/db API_ENCRYPTION_KEY=... python scripts/migrate_files_to_db.py

Переменные окружения:
  DATABASE_URL          - PostgreSQL connection string (обязательно)
  API_ENCRYPTION_KEY    - Fernet key для шифрования API ключей (обязательно)
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Проверка без внесения изменений в БД'
    )
    
    parser.add_argument(
        '--db-url',
        help='PostgreSQL connection string (или через DATABASE_URL env)'
    )
    
    parser.add_argument(
        '--encryption-key',
        help='Fernet encryption key (или через API_ENCRYPTION_KEY env)'
    )
    
    args = parser.parse_args()
    
    # Получаем настройки
    db_url = args.db_url or os.getenv('DATABASE_URL')
    encryption_key = args.encryption_key or os.getenv('API_ENCRYPTION_KEY')
    
    if not db_url:
        logger.error("❌ DATABASE_URL не указан (используйте --db-url или переменную окружения)")
        sys.exit(1)
    
    if not encryption_key:
        logger.error("❌ API_ENCRYPTION_KEY не указан (используйте --encryption-key или переменную окружения)")
        logger.info("Для генерации ключа выполните: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        sys.exit(1)
    
    # Валидация encryption key
    try:
        Fernet(encryption_key.encode())
    except Exception as e:
        logger.error(f"❌ Неверный формат API_ENCRYPTION_KEY: {e}")
        sys.exit(1)
    
    # Запускаем миграцию
    migrator = FilesToDBMigrator(db_url, encryption_key, dry_run=args.dry_run)
    stats = migrator.run()
    
    # Возвращаем код выхода
    if stats.documents_errors > 0 or stats.api_keys_errors > 0 or stats.models_errors > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
