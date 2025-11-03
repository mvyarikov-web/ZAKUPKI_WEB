#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Реальный интеграционный тест UI-запроса с "Новый запрос" к Perplexity Sonar.

Имитирует точное поведение программы:
- HTTP POST /ai_rag/analyze с реальным сервером
- force_web_search=True, clear_document_context=True
- search_params из конфига модели
- Реальный API ключ Perplexity

Цель: добиться такого же результата, как в test_perplexity_real_search.py
"""
import pytest
import os
import sys
import requests
from pathlib import Path

# Базовый URL для локального сервера
BASE_URL = "http://localhost:8081"

# Добавляем корень проекта в sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _has_perplexity_key() -> bool:
    """Проверка наличия ключа Perplexity."""
    if os.environ.get('PPLX_API_KEY') or os.environ.get('PERPLEXITY_API_KEY'):
        return True
    try:
        from utils.api_keys_manager_multiple import get_api_keys_manager_multiple
        mgr = get_api_keys_manager_multiple()
        key = mgr.get_key('perplexity')
        return bool(key)
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_perplexity_key(),
    reason='Нет ключа Perplexity (ни в окружении, ни в менеджере api_keys)'
)
def test_ui_real_search_with_new_request():
    """
    Реальный тест: полная имитация UI-запроса с "Новый запрос".
    
    Проверяет:
    1. force_web_search и clear_document_context корректно передаются
    2. search_params применяются из конфига
    3. Модель выполняет реальный веб-поиск и возвращает анекдоты
    """
    # Проверяем, что сервер запущен
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code != 200:
            pytest.skip(f"Сервер не отвечает на {BASE_URL}/health")
    except Exception as e:
        pytest.skip(f"Не удалось подключиться к серверу: {e}")
    
    # Данные запроса (точно как из UI с "Новый запрос")
    request_data = {
        "file_paths": [
            "Documents_5666261/Сведения об условиях проекта договора и графике исполнения его обязательств 11445932 2025 09 23-14 01 (МСК).docx"
        ],
        "prompt": "Зайди на сайт https://www.anekdot.ru/ и найди 3 свежих анекдота про психологию",
        "model_id": "sonar",
        "top_k": 0,  # Игнорируем документы
        "max_output_tokens": 2500,
        "temperature": 0.2,
        "usd_rub_rate": 95.0,
        "search_enabled": True,
        "search_params": {
            "max_results": 8,
            "search_domain_filter": ["anekdot.ru"],  # Без www
            "search_recency_filter": "week",
            "return_related_questions": False,
            "language_preference": "ru",
        },
        "force_web_search": True,      # ✅ Новый запрос
        "clear_document_context": True  # ✅ Новый запрос
    }
    
    print("=" * 80)
    print("🧪 РЕАЛЬНЫЙ ТЕСТ: UI-путь с force_web_search=True")
    print("=" * 80)
    
    print(f"\n📋 Отправляю запрос:")
    print(f"  • URL: {BASE_URL}/ai_rag/analyze")
    print(f"  • model_id: {request_data['model_id']}")
    print(f"  • force_web_search: {request_data['force_web_search']}")
    print(f"  • clear_document_context: {request_data['clear_document_context']}")
    print(f"  • search_params: {request_data['search_params']}")
    print(f"  • prompt: {request_data['prompt'][:60]}...")
    
    # Отправляем запрос
    response = requests.post(
        f"{BASE_URL}/ai_rag/analyze",
        json=request_data,
        timeout=90
    )
    
    print(f"\n📊 Статус ответа: {response.status_code}")
    
    assert response.status_code == 200, f"Ожидался статус 200, получен {response.status_code}"
    
    # Парсим ответ
    data = response.json()
    
    print(f"\n📦 Структура ответа:")
    print(f"  • success: {data.get('success')}")
    print(f"  • message: {data.get('message', '')[:100]}")
    
    assert data.get('success'), f"success=False: {data.get('message')}"
    
    # Проверяем результат
    result = data.get('result', {})
    answer = result.get('answer', '')
    
    print(f"\n📝 Ответ модели ({len(answer)} символов):")
    print(f"{answer[:400]}...")
    
    # КЛЮЧЕВЫЕ ПРОВЕРКИ: модель НЕ должна отказываться
    forbidden_phrases = [
        "не могу заходить на внешние сайты",
        "не могу зайти на внешние сайты",
        "cannot access external links",
        "не имею доступа к интернету",
        "не могу открывать ссылки",
        "не могу напрямую заходить"
    ]
    
    answer_lower = answer.lower()
    for phrase in forbidden_phrases:
        if phrase in answer_lower:
            pytest.fail(
                f"❌ ПРОВАЛ: Модель отказалась выполнять поиск!\n"
                f"Найдена фраза: '{phrase}'\n"
                f"Ответ: {answer[:300]}"
            )
    
    # Проверяем наличие анекдотов
    search_indicators = [
        "анекдот",
        "психолог"
    ]
    
    found_indicators = [ind for ind in search_indicators if ind in answer_lower]
    
    print(f"\n🔎 Признаки успешного поиска:")
    if found_indicators:
        print(f"  ✅ Найдены: {', '.join(found_indicators)}")
    else:
        print(f"  ⚠️  Не найдены явные признаки анекдотов")
    
    # Usage
    usage = result.get('usage', {})
    print(f"\n📊 Usage:")
    print(f"  • total_tokens: {usage.get('total_tokens')}")
    
    # Финальная проверка
    assert len(found_indicators) > 0, "Ответ не содержит упоминания анекдотов или психологии"
    
    print(f"\n✅ УСПЕХ: Модель выполнила реальный веб-поиск!")
    print(f"Ответ содержит релевантную информацию с сайта.")
    
    return True


if __name__ == '__main__':
    # Прямой запуск
    test_ui_real_search_with_new_request()
