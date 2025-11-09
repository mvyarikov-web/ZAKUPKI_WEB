"""Скрипт полной очистки данных RAG/поиска из PostgreSQL.

Удаляет содержимое бизнес-таблиц: документы, чанки, история поиска, очереди задач,
логи и статистику. Пользователи и их сессии сохраняются.

Запуск:
    python scripts/reset_rag_db.py <DATABASE_URL>

Если переменная окружения DATABASE_URL установлена, аргумент можно опустить.

Безопасность:
    - Использует TRUNCATE ... RESTART IDENTITY CASCADE для каскадного удаления.
    - Проверяет существование таблиц перед очисткой (на случай частичных миграций).
    - Выводит статистику до и после.
"""
from __future__ import annotations

import os
import sys
import psycopg2
from typing import List


TARGET_TABLES: List[str] = [
    # Порядок не критичен при CASCADE, но сначала зависимые ради информативного вывода
    'chunks',
    'documents',
    # Добавлены: user_documents (связи видимости), folder_index_status (статус индексации папок на пользователя)
    'user_documents',
    'folder_index_status',
    'search_history',
    'ai_messages',
    'ai_conversations',
    'job_queue',
    'app_logs',
    'http_request_logs',
    'error_logs',
    'token_usage',
    'prompts',
    'api_keys',
    'user_models',
]


def get_database_url(argv: List[str]) -> str:
    if len(argv) > 1:
        return argv[1]
    env_url = os.getenv('DATABASE_URL')
    if env_url:
        return env_url
    print('Ошибка: не указан DATABASE_URL (аргумент или переменная окружения).', file=sys.stderr)
    sys.exit(1)


def fetch_existing_tables(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename FROM pg_catalog.pg_tables
            WHERE schemaname = 'public';
        """)
        return {r[0] for r in cur.fetchall()}


def count_rows(conn, table: str) -> int:
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM {table};')
            return cur.fetchone()[0]
    except Exception:
        return -1


def main(argv: List[str]) -> None:
    db_url = get_database_url(argv)
    conn = psycopg2.connect(db_url)
    try:
        existing = fetch_existing_tables(conn)
        # Если нужно сохранить prompts, уважим флаг из окружения
        preserve_prompts = os.getenv('PRESERVE_PROMPTS', '0') == '1'
        effective_tables = list(TARGET_TABLES)
        if preserve_prompts and 'prompts' in effective_tables:
            effective_tables.remove('prompts')

        to_truncate = [t for t in effective_tables if t in existing]
        if not to_truncate:
            print('Нет целевых таблиц для очистки (возможно схема не применилась).')
            return

        print('Статистика ДО очистки:')
        for t in to_truncate:
            cnt = count_rows(conn, t)
            if cnt >= 0:
                print(f'  {t}: {cnt} строк')
            else:
                print(f'  {t}: недоступно')

        with conn.cursor() as cur:
            # Формируем единый TRUNCATE
            truncate_sql = 'TRUNCATE TABLE ' + ', '.join(to_truncate) + ' RESTART IDENTITY CASCADE;'
            cur.execute(truncate_sql)
        conn.commit()

        print('\nОчистка выполнена. Статистика ПОСЛЕ:')
        for t in to_truncate:
            cnt = count_rows(conn, t)
            if cnt >= 0:
                print(f'  {t}: {cnt} строк')
            else:
                print(f'  {t}: недоступно')

        if preserve_prompts:
            print('\nГотово. Пользователи, сессии и prompts сохранены.')
        else:
            print('\nГотово. Пользователи и сессии сохранены.')
    finally:
        conn.close()


if __name__ == '__main__':
    main(sys.argv)
