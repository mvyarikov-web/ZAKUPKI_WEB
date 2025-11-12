"""Интеграционный тест подсветки терминов в /view/<path>?q=...

Проверяет на реальных данных (БД-first режим):
1. Выполняется поиск по термину 'договор' (частотный термин).
2. Берётся первый доступный результат (не soft-deleted).
3. Открывается /view/<path>?q=договор,мо
4. Проверяется:
   - статус 200
   - наличие JavaScript-кода подсветки (const q = params.get('q');)
   - наличие combinedRegex
   - наличие термина 'договор' в тексте (>= 1)
   - отсутствие server-side подсветки до выполнения JS (<mark class="highlight"> отсутствует)

Если документов нет или поиск не дал результатов — тест делает skip.

Тест НЕ эмулирует выполнение JS (для этого нужен браузер),
он валидирует подготовку страницы и исходный контент.
"""

from __future__ import annotations

import pytest
from urllib.parse import quote


SEARCH_TERM_PRIMARY = "договор"
SEARCH_TERM_SECONDARY = "мо"


def _get_first_searchable_path(client, owner_id: int) -> str | None:
    """Выполнить поиск и вернуть storage_url первого документа.

    Возвращает None если результатов нет.
    """
    resp = client.post(
        '/search',
        json={'search_terms': SEARCH_TERM_PRIMARY, 'exclude_mode': False},
        headers={'X-User-ID': str(owner_id)}
    )
    if resp.status_code != 200:
        pytest.skip(f"Поиск недоступен: status={resp.status_code}")
    data = resp.get_json() or {}
    results = data.get('results', [])
    if not results:
        pytest.skip("Поиск не вернул результатов — нечего проверять")
    # Берём первый результат
    return results[0].get('storage_url') or results[0].get('path') or results[0].get('file')


def _extract_content_block(html: str) -> str:
    """Извлечь содержимое блока <div class="content" id="docContent"> ... </div>.
    Возвращает пустую строку если не найдено.
    """
    import re
    m = re.search(r'<div class="content" id="docContent">(.*?)</div>', html, re.DOTALL)
    return m.group(1) if m else ""


@pytest.mark.integration
def test_view_highlight_real(client, app, auth_client):
    """Проверка подготовки страницы для подсветки терминов.

    1) Поиск по 'договор'
    2) Открытие /view/<path>?q=договор,мо
    3) Валидация структуры и содержимого
    """
    # Определяем owner_id так же, как в других интеграционных тестах
    from webapp.config.config_service import get_config
    config = get_config()
    owner_id = int(getattr(config, 'default_user_id', 1))

    storage_url = _get_first_searchable_path(client, owner_id)
    if not storage_url:
        # Fallback: загружаем документ с нужными терминами и пересобираем индекс
        from io import BytesIO
        content = (
            "Это тестовый документ для проверки подсветки.\n"
            "Содержит ключевые слова: договор и мо.\n"
            "Договор должен встречаться несколько раз: договор, Договор, ДОГОВОР.\n"
        ).encode('utf-8')
        data = {
            'files': (BytesIO(content), 'real_highlight_test.txt')
        }
        up = auth_client.post('/upload', data=data, content_type='multipart/form-data')
        assert up.status_code == 200, up.get_data(as_text=True)
        bi = auth_client.post('/build_index', json={'force_rebuild': True})
        assert bi.status_code == 200, bi.get_data(as_text=True)
        # Повторяем поиск
        storage_url = _get_first_searchable_path(client, owner_id)
        if not storage_url:
            pytest.skip("Не удалось подготовить документ для проверки /view")

    encoded = quote(storage_url, safe='')
    q_param = f"{SEARCH_TERM_PRIMARY},{SEARCH_TERM_SECONDARY}"
    resp = client.get(f"/view/{encoded}?q={q_param}", headers={'X-User-ID': str(owner_id)})
    assert resp.status_code == 200, f"/view не открылся: status={resp.status_code} body={resp.data[:200]}"

    html = resp.data.decode('utf-8', errors='replace')
    assert 'const q = params.get' in html, "JS-код подсветки (const q = params.get) отсутствует"
    assert 'combinedRegex' in html, "combinedRegex не найден — возможно старая версия шаблона"

    # Извлекаем контент
    content_html = _extract_content_block(html)
    assert content_html, "Контент документа не найден в HTML"

    # Термин должен встречаться хотя бы один раз (частотный в реальных данных)
    lower = content_html.lower()
    count_primary = lower.count(SEARCH_TERM_PRIMARY)
    assert count_primary >= 1, f"Термин '{SEARCH_TERM_PRIMARY}' отсутствует в тексте контента"

    # Сервер не должен делать подсветку сам
    assert '<mark class="highlight">' not in content_html, "Найдена серверная подсветка — должно подсвечивать только JS"

    # Лог для наглядности при -s
    print(f"✅ /view подсветка подготовлена: '{SEARCH_TERM_PRIMARY}' встречается {count_primary} раз, JS присутствует")


if __name__ == "__main__":  # локальный запуск
    pytest.main([__file__, '-v', '-s'])
