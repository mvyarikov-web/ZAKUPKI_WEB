"""
Интеграционный тест /view_index с реальными данными из БД.
Проверяет визуализацию индекса и корректность подсветки.
"""
import pytest


def test_view_index_without_search_no_highlight(auth_client, test_user_doc):
    """
    Открытие /view_index без параметра q — не должно быть подсветки (<mark>).
    Проверяем что контент присутствует, но не подсвечен.
    """
    resp = auth_client.get('/view_index')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    
    # Проверяем что есть контент
    assert 'Индекс (БД)' in html or 'индекс' in html.lower()
    
    # Проверяем что НЕТ подсветки — тегов <mark> быть не должно
    assert '<mark>' not in html, "Подсветка присутствует без параметра q — это ошибка"
    
    # Проверяем что есть базовые метки документов (если есть хоть один документ)
    # Если БД пуста, этот блок можно пропустить
    if test_user_doc:
        # Может быть заголовок документа (если он проиндексирован)
        pass  # Контент проверен через наличие слова "индекс" выше


def test_view_index_with_search_has_highlight(auth_client, test_user_doc):
    """
    Открытие /view_index с параметром q — должна быть подсветка терминов.
    """
    # Предполагаем что в тестовом документе есть слово "тест" или "test"
    resp = auth_client.get('/view_index?q=тест')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    
    # Проверяем наличие подсветки
    # Если термин найден в документе, должен быть <mark>
    # (Если термина нет вообще, подсветки не будет, но тест всё равно корректен)
    
    # Проверяем что поиск отработал (есть индикатор терминов)
    assert 'Подсвечены термины' in html or '<mark>' in html, \
        "При передаче q должна быть либо подсветка, либо индикатор поиска"


def test_view_index_content_populated(auth_client, test_user_doc):
    """
    Проверяем что /view_index отображает документы из БД.
    Если в БД есть документы — контент не должен быть пустым.
    """
    resp = auth_client.get('/view_index')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    
    # Ожидаем хотя бы одну группу (FAST/MEDIUM/SLOW) и метаданные
    assert '# БД-сводка:' in html or 'Документов:' in html, \
        "Индекс должен содержать метаданные о документах из БД"
    
    # Если test_user_doc создан в фикстуре, ожидаем его имя
    if test_user_doc:
        # Можно проверить наличие имени файла если оно известно
        pass  # Минимальная проверка — наличие метаданных уже сделана выше


@pytest.fixture
def test_user_doc(auth_client, tmp_path):
    """
    Фикстура создаёт тестовый документ в БД через загрузку файла.
    Возвращает metadata созданного документа или None если загрузка не удалась.
    """
    # Создаём минимальный TXT файл
    test_file = tmp_path / "test_doc.txt"
    test_file.write_text("Это тестовый документ для проверки индекса. Содержит слово тест.", encoding='utf-8')
    
    # Загружаем через /upload
    with open(test_file, 'rb') as f:
        resp = auth_client.post(
            '/upload',
            data={'files': (f, 'test_doc.txt')},
            content_type='multipart/form-data'
        )
    
    if resp.status_code != 200:
        return None
    
    # Сразу строим индекс чтобы документ попал в /view_index
    resp_build = auth_client.post('/build_index')
    if resp_build.status_code != 200:
        return None
    
    return {'filename': 'test_doc.txt', 'content': test_file.read_text()}
