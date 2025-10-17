"""Сервис для анализа текста по индексу."""
import os
import json
from datetime import datetime
from flask import current_app
from typing import Dict, Any, Optional, Tuple
from document_processor.analysis import Extractor, AnalysisResult


def run_analysis(index_path: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Запускает анализ сводного индекса.
    
    Args:
        index_path: Путь к файлу _search_index.txt
        
    Returns:
        tuple: (success, message, result_dict)
    """
    try:
        if not os.path.exists(index_path):
            return False, f'Индекс не найден: {index_path}', None
        
        current_app.logger.info(f'Запуск анализа индекса: {index_path}')
        
        # Создаём экстрактор
        extractor = Extractor(use_spacy=True)
        
        # Анализируем индекс
        result = extractor.analyze_index(index_path)
        
        # Преобразуем в словарь
        result_dict = result.to_dict()
        
        current_app.logger.info(f'Анализ завершён: извлечено полей с данными')
        
        return True, 'Анализ успешно выполнен', result_dict
        
    except FileNotFoundError as e:
        current_app.logger.error(f'Файл не найден: {e}')
        return False, f'Файл не найден: {e}', None
    except Exception as e:
        current_app.logger.exception(f'Ошибка при анализе: {e}')
        return False, f'Ошибка при анализе: {e}', None


def save_analysis(result_data: Dict[str, Any], index_folder: str) -> Tuple[bool, str, Optional[str]]:
    """
    Сохраняет результаты анализа в JSON и генерирует HTML-отчёт.
    
    Args:
        result_data: Данные анализа (возможно отредактированные пользователем)
        index_folder: Папка для сохранения результатов
        
    Returns:
        tuple: (success, message, report_url)
    """
    try:
        os.makedirs(index_folder, exist_ok=True)
        
        # Сохраняем JSON
        json_path = os.path.join(index_folder, 'analysis_result.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        current_app.logger.info(f'Результаты сохранены в JSON: {json_path}')
        
        # Генерируем HTML-отчёт
        html_path = os.path.join(index_folder, 'analysis_report.html')
        html_content = _generate_html_report(result_data)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        current_app.logger.info(f'HTML-отчёт создан: {html_path}')
        
        # URL для открытия отчёта
        report_url = '/analysis/report/'
        
        return True, 'Результаты успешно сохранены', report_url
        
    except Exception as e:
        current_app.logger.exception(f'Ошибка при сохранении результатов: {e}')
        return False, f'Ошибка при сохранении: {e}', None


def _generate_html_report(data: Dict[str, Any]) -> str:
    """
    Генерирует человекочитаемый HTML-отчёт.
    
    Args:
        data: Данные анализа
        
    Returns:
        HTML-строка
    """
    procurement = data.get('procurement', {})
    sources = data.get('sources', [])
    analysis_date = data.get('analysis_date', datetime.now().isoformat())
    confidence = data.get('confidence', {})
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчёт по анализу закупки</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 20px;
        }}
        .field {{
            margin: 15px 0;
            padding: 10px;
            background-color: #ecf0f1;
            border-radius: 4px;
        }}
        .field-label {{
            font-weight: bold;
            color: #2c3e50;
            margin-right: 10px;
        }}
        .field-value {{
            color: #34495e;
        }}
        .empty {{
            color: #95a5a6;
            font-style: italic;
        }}
        .confidence {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            margin-left: 10px;
        }}
        .confidence-high {{
            background-color: #2ecc71;
            color: white;
        }}
        .confidence-medium {{
            background-color: #f39c12;
            color: white;
        }}
        .confidence-low {{
            background-color: #e74c3c;
            color: white;
        }}
        .items-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .items-table th {{
            background-color: #34495e;
            color: white;
            padding: 10px;
            text-align: left;
        }}
        .items-table td {{
            padding: 10px;
            border-bottom: 1px solid #ecf0f1;
        }}
        .items-table tr:hover {{
            background-color: #f8f9fa;
        }}
        .meta-info {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }}
        .sources {{
            background-color: #e8f4f8;
            padding: 15px;
            border-radius: 4px;
            margin-top: 10px;
        }}
        .sources ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Отчёт по анализу закупки</h1>
        
        <div class="meta-info">
            <strong>Дата анализа:</strong> {_format_datetime(analysis_date)}<br>
            <strong>Количество обработанных документов:</strong> {len(sources)}
        </div>
        
        <div class="sources">
            <strong>Источники данных:</strong>
            <ul>
                {''.join(f'<li>{src}</li>' for src in sources[:10])}
                {f'<li><em>...и ещё {len(sources) - 10} документов</em></li>' if len(sources) > 10 else ''}
            </ul>
        </div>
        
        <h2>Основная информация</h2>
        
        {_render_field('Наименование/Предмет', procurement.get('title'), confidence.get('title'))}
        {_render_field('Номер закупки', procurement.get('number'), confidence.get('number'))}
        {_render_field('ИКЗ', procurement.get('ikz'), confidence.get('ikz'))}
        {_render_field('Номер извещения', procurement.get('notice_number'))}
        
        <h2>Даты</h2>
        
        {_render_field('Дата публикации', procurement.get('publication_date'))}
        {_render_field('Срок подачи заявок', procurement.get('deadline_date'))}
        {_render_field('Дата контракта', procurement.get('contract_date'))}
        
        <h2>Цены</h2>
        
        {_render_field('Начальная (максимальная) цена', _format_price(procurement.get('initial_price'), procurement.get('currency', 'RUB')))}
        {_render_field('Цена контракта', _format_price(procurement.get('contract_price'), procurement.get('currency', 'RUB')))}
        
        <h2>Стороны</h2>
        
        <h3>Заказчик</h3>
        {_render_party(procurement.get('customer'))}
        
        <h3>Поставщик</h3>
        {_render_party(procurement.get('supplier'))}
        
        <h2>Место поставки</h2>
        {_render_address(procurement.get('delivery_address'))}
        
        <h2>Позиции закупки</h2>
        {_render_items(procurement.get('items', []))}
        
        <h2>Условия</h2>
        {_render_terms(procurement.get('terms'))}
        
        <h2>Описание и требования</h2>
        
        {_render_field('Описание предмета закупки', procurement.get('description'))}
        {_render_field('Технические требования', procurement.get('requirements'))}
        {_render_field('Примечания', procurement.get('notes'))}
        
    </div>
</body>
</html>
"""
    
    return html


def _render_field(label: str, value: Any, confidence: Optional[float] = None) -> str:
    """Рендерит поле отчёта."""
    conf_badge = ''
    if confidence is not None:
        conf_class = 'confidence-high' if confidence >= 0.8 else 'confidence-medium' if confidence >= 0.5 else 'confidence-low'
        conf_badge = f'<span class="confidence {conf_class}">{int(confidence * 100)}%</span>'
    
    if value:
        return f'''
        <div class="field">
            <span class="field-label">{label}:</span>
            <span class="field-value">{value}</span>
            {conf_badge}
        </div>
        '''
    else:
        return f'''
        <div class="field">
            <span class="field-label">{label}:</span>
            <span class="empty">не указано</span>
        </div>
        '''


def _render_party(party: Optional[Dict]) -> str:
    """Рендерит информацию о стороне."""
    if not party or not any(party.values()):
        return '<div class="field"><span class="empty">Информация не извлечена</span></div>'
    
    html = ''
    if party.get('name'):
        html += _render_field('Наименование', party['name'])
    if party.get('inn'):
        html += _render_field('ИНН', party['inn'])
    if party.get('kpp'):
        html += _render_field('КПП', party['kpp'])
    if party.get('address'):
        html += _render_field('Адрес', party['address'])
    if party.get('contact'):
        html += _render_field('Контакты', party['contact'])
    
    return html or '<div class="field"><span class="empty">Информация не извлечена</span></div>'


def _render_address(address: Optional[Dict]) -> str:
    """Рендерит адрес."""
    if not address or not any(address.values()):
        return '<div class="field"><span class="empty">Адрес не указан</span></div>'
    
    html = ''
    if address.get('full_address'):
        html += _render_field('Полный адрес', address['full_address'])
    if address.get('region'):
        html += _render_field('Регион', address['region'])
    if address.get('city'):
        html += _render_field('Город', address['city'])
    if address.get('street'):
        html += _render_field('Улица', address['street'])
    
    return html or '<div class="field"><span class="empty">Адрес не указан</span></div>'


def _render_items(items: list) -> str:
    """Рендерит таблицу позиций."""
    if not items:
        return '<div class="field"><span class="empty">Позиции не извлечены</span></div>'
    
    rows = ''
    for item in items:
        rows += f'''
        <tr>
            <td>{item.get('name') or '-'}</td>
            <td>{item.get('okpd2_code') or '-'}</td>
            <td>{item.get('quantity') or '-'}</td>
            <td>{item.get('unit') or '-'}</td>
            <td>{item.get('price_per_unit') or '-'}</td>
            <td>{item.get('total_price') or '-'}</td>
        </tr>
        '''
    
    return f'''
    <table class="items-table">
        <thead>
            <tr>
                <th>Наименование</th>
                <th>Код ОКПД2</th>
                <th>Количество</th>
                <th>Единица</th>
                <th>Цена за ед.</th>
                <th>Общая цена</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    '''


def _render_terms(terms: Optional[Dict]) -> str:
    """Рендерит условия."""
    if not terms or not any(terms.values()):
        return '<div class="field"><span class="empty">Условия не указаны</span></div>'
    
    html = ''
    if terms.get('delivery_terms'):
        html += _render_field('Условия доставки', terms['delivery_terms'])
    if terms.get('warranty'):
        html += _render_field('Гарантия', terms['warranty'])
    if terms.get('installation'):
        html += _render_field('Монтаж/Установка', terms['installation'])
    if terms.get('payment_terms'):
        html += _render_field('Условия оплаты', terms['payment_terms'])
    if terms.get('contract_duration'):
        html += _render_field('Срок контракта', terms['contract_duration'])
    if terms.get('other'):
        html += _render_field('Прочие условия', terms['other'])
    
    return html or '<div class="field"><span class="empty">Условия не указаны</span></div>'


def _format_price(price: Optional[str], currency: str = 'RUB') -> Optional[str]:
    """Форматирует цену."""
    if not price:
        return None
    return f'{price} {currency}'


def _format_datetime(dt_str: str) -> str:
    """Форматирует дату и время."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except Exception:
        return dt_str
