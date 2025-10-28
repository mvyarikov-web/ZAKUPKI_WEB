"""Утилиты для рендеринга Markdown в безопасный HTML."""
import bleach
from markdown import markdown


def render_analysis_result(result_dict: dict) -> str:
    """
    Рендерит результат анализа в красиво отформатированный HTML.
    
    Args:
        result_dict: Словарь с полями answer, cost, usage, model
        
    Returns:
        HTML строка с отформатированным результатом
    """
    # Извлекаем данные
    answer = result_dict.get('answer', '')
    cost = result_dict.get('cost', {})
    usage = result_dict.get('usage', {})
    model = result_dict.get('model', 'unknown')
    
    # Конвертируем Markdown в HTML
    answer_html = markdown(
        answer,
        extensions=['extra', 'nl2br', 'sane_lists', 'tables']
    )
    
    # Санитизация HTML (защита от XSS)
    safe_html = bleach.clean(
        answer_html,
        tags=[
            'p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'table', 'thead', 'tbody', 'tr', 'th', 'td',
            'blockquote', 'code', 'pre', 'hr', 'div', 'span'
        ],
        attributes={
            '*': ['class', 'id'],
            'a': ['href', 'title', 'target'],
            'table': ['border', 'cellpadding', 'cellspacing']
        },
        strip=True
    )
    
    # Формируем метаинформацию
    usd_to_rub = cost.get('usd_to_rub_rate', 95.0)
    
    meta_html = f"""
    <div style="background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 20px; font-size: 14px; border-left: 4px solid #007bff;">
        <div style="margin-bottom: 8px;">
            <strong>Модель:</strong> <span style="color: #007bff;">{model}</span>
        </div>
        <div style="margin-bottom: 8px;">
            <strong>Стоимость USD:</strong> 
            <span style="color: #28a745;">${cost.get('total', 0):.6f}</span>
            <span style="color: #6c757d; font-size: 12px;">
                (вход: ${cost.get('input', 0):.6f}, выход: ${cost.get('output', 0):.6f})
            </span>
        </div>
        <div style="margin-bottom: 8px; padding: 10px; background: linear-gradient(135deg, #e7f5e7 0%, #d4edda 100%); border-radius: 6px; border: 2px solid #28a745; box-shadow: 0 2px 4px rgba(40,167,69,0.2);">
            <strong style="font-size: 15px;">💰 Итого в рублях:</strong> 
            <span style="color: #155724; font-size: 18px; font-weight: bold;">₽{cost.get('total_rub', 0):.2f}</span>
            <span style="color: #6c757d; font-size: 11px; display: block; margin-top: 4px;">
                по курсу ${usd_to_rub:.2f} ₽/$ (вход: ₽{cost.get('input_rub', 0):.2f}, выход: ₽{cost.get('output_rub', 0):.2f})
            </span>
        </div>
        <div>
            <strong>Токены:</strong> 
            <span style="color: #17a2b8;">{usage.get('total_tokens', 0):,}</span>
            <span style="color: #6c757d; font-size: 12px;">
                (вход: {usage.get('input_tokens', 0):,}, выход: {usage.get('output_tokens', 0):,})
            </span>
        </div>
    </div>
    <hr style="margin: 20px 0; border: none; border-top: 1px solid #dee2e6;"/>
    """
    
    # Стили для контента
    content_style = """
    <div style="line-height: 1.6; color: #212529; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    """
    
    return meta_html + content_style + safe_html + "</div>"


def render_plain_text(result_dict: dict) -> str:
    """
    Рендерит результат анализа в простой текстовый формат.
    
    Args:
        result_dict: Словарь с полями answer, cost, usage, model
        
    Returns:
        Текстовая строка для сохранения в файл
    """
    answer = result_dict.get('answer', '')
    cost = result_dict.get('cost', {})
    usage = result_dict.get('usage', {})
    model = result_dict.get('model', 'unknown')
    usd_to_rub = cost.get('usd_to_rub_rate', 95.0)
    
    header = f"""
================================================================================
AI АНАЛИЗ
================================================================================
Модель: {model}
Стоимость USD: ${cost.get('total', 0):.6f} (вход: ${cost.get('input', 0):.6f}, выход: ${cost.get('output', 0):.6f})
💰 ИТОГО В РУБЛЯХ: ₽{cost.get('total_rub', 0):.2f}
   по курсу ${usd_to_rub:.2f} (вход: ₽{cost.get('input_rub', 0):.2f}, выход: ₽{cost.get('output_rub', 0):.2f})
Токены: {usage.get('total_tokens', 0):,} (вход: {usage.get('input_tokens', 0):,}, выход: {usage.get('output_tokens', 0):,})
================================================================================

"""
    
    return header + answer
