"""Базовые тесты для модуля анализа текста."""
import os
import pytest
from document_processor.analysis import Extractor


def test_extractor_initialization():
    """Тест инициализации экстрактора."""
    extractor = Extractor(use_spacy=False)
    assert extractor is not None
    assert extractor.nlp is None  # spaCy не загружен


def test_parse_simple_index(tmp_path):
    """Тест парсинга простого индекса."""
    # Создаём тестовый индекс
    index_content = """===============================
ЗАГОЛОВОК: Тестовый документ.pdf
Формат: pdf | Символов: 100 | Слов: 20
Источник: test.pdf
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Извещение о проведении закупки № 12345-2023
Предмет контракта: Поставка канцелярских товаров
Начальная цена контракта: 150 000 руб.
Дата публикации: 15.10.2023
Заказчик: ООО "Тестовая организация"
ИНН заказчика: 7701234567
<<< КОНЕЦ ДОКУМЕНТА >>>
"""
    
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text(index_content, encoding='utf-8')
    
    # Создаём экстрактор и анализируем
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    # Проверяем результаты
    assert result is not None
    assert result.procurement is not None
    assert len(result.sources) == 1
    assert result.sources[0] == 'Тестовый документ.pdf'
    
    # Проверяем извлечённые данные
    procurement = result.procurement
    assert procurement.number == '12345-2023'
    assert 'канцелярских товаров' in (procurement.title or '')
    assert procurement.initial_price == '150 000'
    assert procurement.publication_date == '15.10.2023'
    
    # Проверяем заказчика
    assert procurement.customer is not None
    assert 'Тестовая организация' in (procurement.customer.name or '')
    assert procurement.customer.inn == '7701234567'


def test_parse_multiple_documents(tmp_path):
    """Тест парсинга индекса с несколькими документами."""
    index_content = """===============================
ЗАГОЛОВОК: Документ1.pdf
Формат: pdf | Символов: 50 | Слов: 10
Источник: doc1.pdf
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Извещение № 111
Предмет: Поставка оборудования
<<< КОНЕЦ ДОКУМЕНТА >>>
===============================
ЗАГОЛОВОК: Документ2.txt
Формат: txt | Символов: 40 | Слов: 8
Источник: doc2.txt
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Контракт № 222
НМЦК: 200 000 руб.
<<< КОНЕЦ ДОКУМЕНТА >>>
"""
    
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text(index_content, encoding='utf-8')
    
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    assert result is not None
    assert len(result.sources) == 2
    assert 'Документ1.pdf' in result.sources
    assert 'Документ2.txt' in result.sources
    
    # Проверяем, что данные из обоих документов были учтены
    procurement = result.procurement
    # Должен быть найден хотя бы один номер
    assert procurement.number is not None


def test_empty_index(tmp_path):
    """Тест обработки пустого индекса."""
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text("", encoding='utf-8')
    
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    # Не должно быть ошибок, просто пустой результат
    assert result is not None
    assert len(result.sources) == 0


def test_index_not_found():
    """Тест обработки отсутствующего индекса."""
    extractor = Extractor(use_spacy=False)
    
    with pytest.raises(FileNotFoundError):
        extractor.analyze_index('/nonexistent/path/index.txt')


def test_extract_okpd_codes(tmp_path):
    """Тест извлечения кодов ОКПД2."""
    index_content = """===============================
ЗАГОЛОВОК: test.pdf
Формат: pdf | Символов: 100 | Слов: 20
Источник: test.pdf
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Позиция 1: Компьютеры
ОКПД2: 26.20.11.110
Количество: 10 шт

Позиция 2: Мониторы
Код ОКПД2: 26.20.13.120
Количество: 15 шт
<<< КОНЕЦ ДОКУМЕНТА >>>
"""
    
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text(index_content, encoding='utf-8')
    
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    # Проверяем извлечение позиций
    assert result.procurement.items is not None
    assert len(result.procurement.items) >= 2
    
    # Проверяем коды ОКПД2
    okpd_codes = [item.okpd2_code for item in result.procurement.items if item.okpd2_code]
    assert '26.20.11.110' in okpd_codes
    assert '26.20.13.120' in okpd_codes


def test_confidence_calculation(tmp_path):
    """Тест расчёта уверенности в извлечённых данных."""
    index_content = """===============================
ЗАГОЛОВОК: test.pdf
Формат: pdf | Символов: 100 | Слов: 20
Источник: test.pdf
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Извещение № 12345
ИКЗ: 123456789012345678901234567890123456
Предмет: Поставка товаров
Заказчик: ООО "Компания"
Начальная цена: 100 000 руб.
<<< КОНЕЦ ДОКУМЕНТА >>>
"""
    
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text(index_content, encoding='utf-8')
    
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    # Проверяем наличие показателей уверенности
    assert result.confidence is not None
    assert isinstance(result.confidence, dict)
    
    # Для извлечённых полей уверенность должна быть выше 0
    if result.procurement.number:
        assert result.confidence.get('number', 0) > 0
    if result.procurement.ikz:
        assert result.confidence.get('ikz', 0) > 0


def test_to_dict_conversion(tmp_path):
    """Тест конвертации результата в словарь."""
    index_content = """===============================
ЗАГОЛОВОК: test.pdf
Формат: pdf | Символов: 50 | Слов: 10
Источник: test.pdf
===============================
<<< НАЧАЛО ДОКУМЕНТА >>>
Извещение № 999
Предмет: Тестовая закупка
<<< КОНЕЦ ДОКУМЕНТА >>>
"""
    
    index_path = tmp_path / "_search_index.txt"
    index_path.write_text(index_content, encoding='utf-8')
    
    extractor = Extractor(use_spacy=False)
    result = extractor.analyze_index(str(index_path))
    
    # Конвертируем в словарь
    result_dict = result.to_dict()
    
    # Проверяем структуру
    assert isinstance(result_dict, dict)
    assert 'procurement' in result_dict
    assert 'sources' in result_dict
    assert 'highlights' in result_dict
    assert 'analysis_date' in result_dict
    assert 'confidence' in result_dict
    
    # Проверяем, что procurement тоже словарь
    assert isinstance(result_dict['procurement'], dict)
