#!/usr/bin/env python3
"""
Тест проверки подсветки всех найденных слов в просмотре индекса.

Проверяет, что JavaScript в view.html корректно подсвечивает все термины поиска.
"""

import requests
from urllib.parse import quote
import re


def test_highlight_all_terms():
    """Тест: все термины из параметра ?q должны подсвечиваться в view.html"""
    
    # 1. Выполняем поиск по нескольким терминам
    search_terms = ['мо', 'договор']
    resp = requests.post(
        'http://127.0.0.1:8081/search',
        json={'search_terms': search_terms},
        headers={'X-User-ID': '512'}
    )
    
    assert resp.status_code == 200, f"Search failed: {resp.status_code}"
    
    results = resp.json().get('results', [])
    assert len(results) > 0, "No search results found"
    
    # 2. Берём первый документ
    doc = results[0]
    path = doc['storage_url']
    
    # 3. Открываем страницу просмотра с терминами
    terms_query = ','.join(search_terms)
    encoded_path = quote(path)
    view_url = f'http://127.0.0.1:8081/view/{encoded_path}?q={terms_query}'
    
    view_resp = requests.get(view_url, headers={'X-User-ID': '512'})
    assert view_resp.status_code == 200, f"View failed: {view_resp.status_code}"
    
    html = view_resp.text
    
    # 4. Проверяем, что JavaScript присутствует
    assert 'const q = params.get(\'q\');' in html, "JavaScript для подсветки не найден"
    
    # 5. Проверяем, что создаётся объединённое регулярное выражение
    assert 'combinedRegex' in html, "Объединённое регулярное выражение не создаётся"
    
    # 6. Проверяем, что нет устаревшего кода с множественными regex
    assert 'const regexes = terms.map' not in html, "Устаревший код с множественными regex всё ещё присутствует"
    
    # 7. Проверяем, что бэкенд не выполняет подсветку (0 mark тегов в исходном HTML)
    # Исключаем mark из CSS и комментариев
    content_start = html.find('<div class="content"')
    content_end = html.find('</div>', content_start)
    content_section = html[content_start:content_end] if content_start != -1 else ''
    
    # В content до выполнения JS не должно быть mark с классом highlight
    backend_marks = content_section.count('<mark class="highlight">')
    assert backend_marks == 0, f"Бэкенд не должен создавать подсветку, найдено {backend_marks} тегов"
    
    print("✅ Все проверки пройдены:")
    print(f"   • JavaScript для подсветки присутствует")
    print(f"   • Используется объединённое регулярное выражение")
    print(f"   • Бэкенд не выполняет подсветку")
    print(f"   • Тестовый документ: {doc['filename']}")
    print(f"   • URL для проверки: {view_url}")


if __name__ == '__main__':
    try:
        test_highlight_all_terms()
        print("\n🎉 Тест успешно пройден!")
    except AssertionError as e:
        print(f"\n❌ Тест провален: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        exit(1)
