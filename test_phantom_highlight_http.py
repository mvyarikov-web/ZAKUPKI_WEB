#!/usr/bin/env python3
"""
Простой тест фантомной подсветки через HTTP и проверку HTML.
Без Selenium - просто запросы к серверу.
"""
import sys
import requests
from bs4 import BeautifulSoup
import re

def test_highlights_in_html():
    """Проверка наличия .highlight в HTML."""
    
    print("="*80)
    print("ТЕСТ: Проверка фантомной подсветки в HTML")
    print("="*80)
    
    try:
        # Запрос главной страницы
        print("\n1️⃣ Загрузка главной страницы...")
        resp = requests.get('http://127.0.0.1:8081', timeout=10)
        
        if resp.status_code != 200:
            print(f"❌ Ошибка: статус {resp.status_code}")
            return False
        
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем .context-snippet в исходном HTML
        snippets = soup.find_all(class_='context-snippet')
        print(f"   Найдено .context-snippet в HTML: {len(snippets)}")
        
        # Ищем .highlight в исходном HTML
        highlights = soup.find_all(class_='highlight')
        print(f"   Найдено .highlight в HTML: {len(highlights)}")
        
        if len(highlights) > 0:
            print(f"\n❌ ПРОБЛЕМА: В исходном HTML уже есть {len(highlights)} элементов .highlight!")
            for i, hl in enumerate(highlights[:5], 1):
                text = hl.get_text()[:50]
                parent = hl.parent
                print(f"      Highlight {i}: '{text}' в <{parent.name} class='{parent.get('class')}'>")
            print("\n   ⚠️  Это означает что подсветка генерируется на сервере, а не в JS!")
        else:
            print("   ✅ В исходном HTML нет .highlight (правильно)")
        
        # Проверяем наличие скрипта с clearHighlights
        print("\n2️⃣ Проверка наличия script.js...")
        scripts = soup.find_all('script', src=re.compile(r'script\.js'))
        if scripts:
            print(f"   ✅ Найдено script.js: {len(scripts)} раз(а)")
        else:
            print("   ❌ script.js НЕ найден!")
        
        # Проверяем загружается ли clearHighlights
        script_resp = requests.get('http://127.0.0.1:8081/static/js/script.js', timeout=5)
        if script_resp.status_code == 200:
            script_content = script_resp.text
            has_clear = 'function clearHighlights' in script_content
            has_highlight = 'function highlightSnippets' in script_content
            
            print(f"   function clearHighlights найдена: {has_clear}")
            print(f"   function highlightSnippets найдена: {has_highlight}")
            
            # Ищем вызовы clearHighlights
            clear_calls = script_content.count('clearHighlights()')
            print(f"   Вызовов clearHighlights(): {clear_calls}")
            
            if clear_calls == 0:
                print("   ❌ clearHighlights НЕ вызывается нигде!")
            else:
                # Показываем контексты вызовов
                lines = script_content.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'clearHighlights()' in line:
                        context_start = max(0, i - 3)
                        context_end = min(len(lines), i + 2)
                        print(f"\n   📍 Вызов на строке {i}:")
                        for j in range(context_start, context_end):
                            marker = ">>> " if j == i - 1 else "    "
                            print(f"   {marker}{lines[j]}")
        else:
            print(f"   ❌ Не удалось загрузить script.js: {script_resp.status_code}")
        
        # Теперь проверим что происходит после поиска
        print("\n3️⃣ Симуляция поиска через /search...")
        search_resp = requests.post(
            'http://127.0.0.1:8081/search',
            json={'keywords': ['договор']},
            headers={'X-User-ID': '512'},
            timeout=10
        )
        
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            results = search_data.get('grouped_results', {})
            total = sum(len(v) for v in results.values())
            print(f"   ✅ Поиск выполнен: найдено {total} результатов")
            
            # Проверяем структуру результатов
            if total > 0:
                first_group = next(iter(results.values()), [])
                if first_group:
                    first_result = first_group[0]
                    print(f"   Пример результата: {list(first_result.keys())}")
                    
                    # Проверяем есть ли highlight в snippet
                    snippet = first_result.get('snippet', '')
                    if '<span class="highlight">' in snippet or '<mark' in snippet:
                        print(f"   ⚠️  ВНИМАНИЕ: Сервер возвращает snippet с подсветкой!")
                        print(f"   Фрагмент: {snippet[:100]}...")
                    else:
                        print(f"   ✅ Snippet без подсветки (правильно)")
        else:
            print(f"   ❌ Ошибка поиска: {search_resp.status_code}")
        
        print("\n" + "="*80)
        print("ВЫВОДЫ:")
        print("="*80)
        
        if len(highlights) > 0:
            print("❌ Подсветка присутствует в исходном HTML страницы")
            print("   → Проблема НЕ в JavaScript, а в серверном рендеринге")
            print("   → Нужно проверить шаблоны (templates/*.html)")
            return False
        else:
            print("✅ В исходном HTML подсветки нет")
            print("   → Проблема может быть в:")
            print("     1. JavaScript не вызывает clearHighlights")
            print("     2. Или вызывает, но после highlightSnippets")
            print("     3. Или .context-snippet вообще нет на странице")
            print("\n   💡 Рекомендация: проверить в браузере через DevTools")
            return True
            
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_highlights_in_html()
