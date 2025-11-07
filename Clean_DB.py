"""Утилита очистки БД документов/чанков/истории (лаунчер).

Назначение:
  - Безопасно вызвать scripts/reset_rag_db.py с корректным Python и DSN.
  - Подтвердить действие перед очисткой (защита от случайного запуска).

Использование:
  python Clean_DB.py [--yes] [--dsn POSTGRES_DSN]

Примеры:
  # DSN берётся из .env (DATABASE_URL). Будет задан вопрос подтверждения.
  python Clean_DB.py

  # Без подтверждения (для CI/скриптов):
  python Clean_DB.py --yes

  # Явно указать DSN (переопределяет .env):
  python Clean_DB.py --dsn postgresql://user:pass@localhost:5432/app_db

Заметки:
  - .env читается из корня проекта; если в DATABASE_URL есть схема
    'postgresql+psycopg2://', она будет преобразована в 'postgresql://'.
  - Пользователи и сессии не удаляются; чистятся документы, чанки,
    история, логи, очередь и пр. бизнес-данные.
"""
from __future__ import annotations

import argparse
import os
import sys
import subprocess
from typing import Dict


def load_env_file(env_path: str) -> Dict[str, str]:
    """Простейший парсер .env (KEY=VALUE, без сложных случаев)."""
    env: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return env
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):  # комментарии/пустые
                    continue
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    env[key] = val
    except Exception:
        pass
    return env


def normalize_dsn(dsn: str) -> str:
    # psycopg2 не понимает sqlalchemy-схему; конвертируем при необходимости
    return dsn.replace('postgresql+psycopg2://', 'postgresql://')


def get_python_exec(project_root: str) -> str:
    # Предпочтительно использовать venv, иначе текущий интерпретатор
    venv_python = os.path.join(project_root, '.venv', 'bin', 'python')
    if os.path.exists(venv_python) and os.access(venv_python, os.X_OK):
        return venv_python
    return sys.executable


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Очистка БД документов/чанков/истории')
    parser.add_argument('--yes', action='store_true', help='Пропустить подтверждение')
    parser.add_argument('--dsn', type=str, help='Строка подключения к PostgreSQL')
    args = parser.parse_args(argv)

    project_root = os.path.dirname(os.path.abspath(__file__))
    reset_script = os.path.join(project_root, 'scripts', 'reset_rag_db.py')
    if not os.path.exists(reset_script):
        print('Не найден scripts/reset_rag_db.py. Проверьте репозиторий.', file=sys.stderr)
        return 1

    # Загружаем .env и выставляем в окружение, если переменных ещё нет
    env_file = os.path.join(project_root, '.env')
    env_values = load_env_file(env_file)
    for k, v in env_values.items():
        os.environ.setdefault(k, v)

    dsn = args.dsn or os.environ.get('DATABASE_URL', '')
    if not dsn:
        print('DATABASE_URL не найден в .env и не передан через --dsn', file=sys.stderr)
        return 2

    dsn = normalize_dsn(dsn)

    if not args.yes and not os.environ.get('CLEAN_DB_FORCE'):
        print('ВНИМАНИЕ: Будут удалены документы, чанки, история, логи и бизнес-данные.')
        print('Пользователи и сессии сохраняются.')
        confirm = input('Продолжить? [y/N]: ').strip().lower()
        if confirm not in ('y', 'yes', 'д', 'да'):
            print('Отменено пользователем.')
            return 0

    py_exec = get_python_exec(project_root)
    cmd = [py_exec, reset_script, dsn]
    print(f'Запуск очистки через: {cmd[0]} {reset_script} (dsn скрыт)')
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f'Ошибка при очистке БД: {e}', file=sys.stderr)
        return e.returncode or 1


if __name__ == '__main__':
    sys.exit(main())
