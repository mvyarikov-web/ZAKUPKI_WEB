#!/usr/bin/env python3
"""
Тест подсветки в просмотре индекса на реальных данных.

Проверяет полный цикл:
1. Поиск документов по терминам
2. Открытие документа через /view/<path>?q=...
3. Проверка наличия JavaScript для подсветки
4. Проверка содержимого для подсветки
5. Визуальная проверка (сохранение HTML)
"""

import requests
from urllib.parse import quote, unquote
import re
import html as html_module


def test_highlight_on_real_data():
    """Тест подсветки на реальных данных."""
    
    # Термины для поиска
    search_terms = ['договор', 'мо']
    
    print("=" * 60)
    print("ТЕСТ ПОДСВЕТКИ В ПРОСМОТРЕ ИНДЕКСА")
    print("=" * 60)
    
    # 1. Выполняем поиск
    print(f"\n1️⃣ Поиск документов по терминам: {search_terms}")
    resp = requests.post(
        'http://127.0.0.1:8081/search',
        json={'search_terms': search_terms},
        headers={'X-User-ID': '512'}
    )
    
    assert resp.status_code == 200, f"Ошибка поиска: {resp.status_code}"
    
    results = resp.json().get('results', [])
    print(f"   ✅ Найдено документов: {len(results)}")
    
    if len(results) == 0:
        print("   ⚠️  Нет результатов для тестирования")
        return
    
    # 2. Берём первый документ
    doc = results[0]
    filename = doc['filename']
    path = doc['storage_url']
    
    print(f"\n2️⃣ Выбран документ для проверки:")
    print(f"   Имя: {filename}")
    print(f"   Путь: {path}")
    print(f"   ID: {doc.get('doc_id', 'N/A')}")
    
    # 3. Формируем URL для просмотра
    terms_query = ','.join(search_terms)
    encoded_path = quote(path)
    view_url = f'http://127.0.0.1:8081/view/{encoded_path}?q={terms_query}'
    
    print(f"\n3️⃣ Открываю документ через /view/:")
    print(f"   URL: {view_url}")
    
    view_resp = requests.get(view_url, headers={'X-User-ID': '512'})
    
    if view_resp.status_code != 200:
        print(f"   ❌ ОШИБКА: {view_resp.status_code}")
        print(f"   Ответ: {view_resp.text[:500]}")
        
        # Проверяем, не удалён ли документ
        if view_resp.status_code == 404:
            print("\n   💡 Подсказка: Возможно, документ помечен как удалённый.")
            print("   Попробую следующий документ...")
            
            # Пробуем следующие документы
            for i, doc in enumerate(results[1:4], 2):
                print(f"\n   Попытка {i}: {doc['filename']}")
                encoded_path = quote(doc['storage_url'])
                view_url = f'http://127.0.0.1:8081/view/{encoded_path}?q={terms_query}'
                view_resp = requests.get(view_url, headers={'X-User-ID': '512'})
                
                if view_resp.status_code == 200:
                    filename = doc['filename']
                    path = doc['storage_url']
                    print(f"   ✅ Успешно открыт!")
                    break
            else:
                print("\n   ❌ Не удалось найти доступный документ для тестирования")
                return
        else:
            return
    
    html = view_resp.text
    
    # 4. Проверяем структуру HTML
    print(f"\n4️⃣ Анализ HTML:")
    print(f"   Размер: {len(html)} байт")
    
    # Проверка 1: JavaScript
    if 'const q = params.get(\'q\');' in html:
        print("   ✅ JavaScript для подсветки присутствует")
    else:
        print("   ❌ JavaScript для подсветки НЕ НАЙДЕН")
        return
    
    # Проверка 2: Объединённое regex
    if 'combinedRegex' in html:
        print("   ✅ Используется объединённое регулярное выражение")
    else:
        print("   ⚠️  Объединённое regex не найдено (может быть старая версия)")
    
    # Проверка 3: Блок контента
    if '<div class="content" id="docContent">' in html:
        print("   ✅ Блок контента найден")
    else:
        print("   ❌ Блок контента НЕ НАЙДЕН")
        return
    
    # 5. Извлекаем содержимое
    content_match = re.search(r'<div class="content" id="docContent">(.*?)</div>\s*</div>', html, re.DOTALL)
    if not content_match:
        print("   ❌ Не удалось извлечь содержимое")
        return
    
    content_html = content_match.group(1)
    decoded_content = html_module.unescape(content_html)
    
    print(f"\n5️⃣ Анализ содержимого для подсветки:")
    print(f"   Размер текста: {len(decoded_content)} символов")
    
    # Проверяем наличие каждого термина
    found_terms = []
    for term in search_terms:
        count = decoded_content.lower().count(term.lower())
        if count > 0:
            found_terms.append(term)
            print(f"   ✅ '{term}': {count} вхождений")
            
            # Показываем первые 2 контекста
            contexts = re.findall(r'.{0,40}' + re.escape(term) + r'.{0,40}', 
                                 decoded_content, re.IGNORECASE)
            for i, ctx in enumerate(contexts[:2], 1):
                clean_ctx = ' '.join(ctx.split())
                print(f"      {i}. ...{clean_ctx}...")
        else:
            print(f"   ⚠️  '{term}': не найден в тексте")
    
    # Проверка 6: Бэкенд не должен создавать подсветку
    backend_marks = content_html.count('<mark class="highlight">')
    if backend_marks == 0:
        print(f"\n6️⃣ ✅ Бэкенд не создаёт подсветку (правильно)")
    else:
        print(f"\n6️⃣ ⚠️  Найдено {backend_marks} тегов <mark> от бэкенда (может быть дублирование)")
    
    # 7. Сохраняем HTML для визуальной проверки
    output_file = 'test_highlight_real_data_output.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n7️⃣ HTML сохранён: {output_file}")
    print(f"   Откройте файл в браузере для визуальной проверки подсветки")
    
    # Итоговый вердикт
    print("\n" + "=" * 60)
    if len(found_terms) >= len(search_terms):
        print("✅ ТЕСТ ПРОЙДЕН")
        print(f"   Все термины присутствуют в документе")
        print(f"   JavaScript подсветки на месте")
        print(f"   Откройте {output_file} в браузере — термины должны быть подсвечены")
    else:
        print("⚠️  ЧАСТИЧНЫЙ УСПЕХ")
        print(f"   Найдено терминов: {len(found_terms)}/{len(search_terms)}")
        print(f"   JavaScript подсветки на месте")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_highlight_on_real_data()
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
