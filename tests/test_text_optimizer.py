"""
Тесты для сервиса оптимизации текста
"""
import pytest
from webapp.services.text_optimizer import TextOptimizer, OptimizationResult


class TestTextOptimizer:
    """Тесты оптимизатора текста"""
    
    @pytest.fixture
    def optimizer(self):
        """Фикстура оптимизатора"""
        return TextOptimizer()
    
    def test_empty_text(self, optimizer):
        """Тест пустого текста"""
        result = optimizer.optimize('')
        assert result.optimized_text == ''
        assert result.chars_before == 0
        assert result.chars_after == 0
        assert result.reduction_pct == 0.0
    
    def test_normalize_whitespace(self, optimizer):
        """Тест нормализации пробелов"""
        text = "Текст  с   множественными    пробелами"
        result = optimizer.optimize(text)
        assert "  " not in result.optimized_text
        assert result.optimized_text == "Текст с множественными пробелами"
    
    def test_remove_decorative_lines(self, optimizer):
        """Тест удаления декоративных линий"""
        text = """Заголовок
=============================
Содержание
-----------------------------
Футер
_____________________________"""
        result = optimizer.optimize(text)
        assert "=====" not in result.optimized_text
        assert "-----" not in result.optimized_text
        assert "_____" not in result.optimized_text
        assert "Заголовок" in result.optimized_text
        assert "Содержание" in result.optimized_text
        assert "Футер" in result.optimized_text
    
    def test_remove_page_numbers(self, optimizer):
        """Тест удаления номеров страниц"""
        text = """Текст документа
Стр. 1 из 10
Продолжение текста
Page 2 of 10
Окончание"""
        result = optimizer.optimize(text)
        assert "Стр." not in result.optimized_text
        assert "Page" not in result.optimized_text
        assert "Текст документа" in result.optimized_text
        assert "Продолжение текста" in result.optimized_text
        assert "Окончание" in result.optimized_text
    
    def test_fix_hyphen_breaks(self, optimizer):
        """Тест склейки дефисных переносов"""
        text = """Это длинное сло-
во было разбито переносом"""
        result = optimizer.optimize(text)
        assert "слово" in result.optimized_text
        assert "сло-\nво" not in result.optimized_text
    
    def test_preserve_compound_words(self, optimizer):
        """Тест сохранения составных слов"""
        text = "Бизнес-план компании"
        result = optimizer.optimize(text)
        # Составные слова с дефисом должны сохраниться
        assert "Бизнес" in result.optimized_text or "бизнес" in result.optimized_text
    
    def test_remove_repeated_headers(self, optimizer):
        """Тест удаления повторяющихся хедеров"""
        text = """Заголовок документа
Заголовок документа
Заголовок документа
Основной текст
Заголовок документа"""
        result = optimizer.optimize(text)
        # Должно остаться только одно вхождение
        assert result.optimized_text.count("Заголовок документа") == 1
        assert "Основной текст" in result.optimized_text
    
    def test_preserve_technical_data(self, optimizer):
        """Тест сохранения технических данных"""
        text = """Артикул: АБВ-123
Дата: 31.10.2025
ГОСТ 12345-67
Размер: 100x200 мм
Цена: 1500.50 руб."""
        result = optimizer.optimize(text)
        # Все технические данные должны сохраниться
        assert "АБВ-123" in result.optimized_text
        assert "31.10.2025" in result.optimized_text
        assert "ГОСТ 12345-67" in result.optimized_text
        assert "100x200" in result.optimized_text
        assert "1500.50" in result.optimized_text
    
    def test_normalize_punctuation(self, optimizer):
        """Тест нормализации пунктуации"""
        text = "Текст с длинным тире — и коротким - дефисом"
        result = optimizer.optimize(text)
        # Все тире должны стать короткими дефисами
        assert "—" not in result.optimized_text
        assert "-" in result.optimized_text
    
    def test_unify_list_markers(self, optimizer):
        """Тест унификации маркеров списков"""
        text = """• Первый пункт
* Второй пункт
- Третий пункт
– Четвёртый пункт"""
        result = optimizer.optimize(text)
        # Все маркеры должны стать "- "
        lines = result.optimized_text.split('\n')
        for line in lines:
            if line.strip():
                assert line.strip().startswith('- ')
    
    def test_multiple_newlines(self, optimizer):
        """Тест схлопывания пустых строк"""
        text = """Первый абзац


Второй абзац




Третий абзац"""
        result = optimizer.optimize(text)
        # Не должно быть более 2 переводов строк подряд
        assert "\n\n\n" not in result.optimized_text
        assert "Первый абзац" in result.optimized_text
        assert "Второй абзац" in result.optimized_text
        assert "Третий абзац" in result.optimized_text
    
    def test_realistic_document(self, optimizer):
        """Тест на реалистичном документе"""
        text = """=================================
         ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ
=================================
Стр. 1 из 5

Артикул: ТВ-2024-001
Наименование: Телевизор
Диагональ: 55 дюймов
Разрешение: 3840x2160
Цена: 45990.00 руб.

-----------------------------

Стр. 2 из 5
Дополнительные харак-
теристики товара

• Смарт ТВ
* HDR поддержка
- Wi-Fi встроенный
– Bluetooth 5.0

=================================
         ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ
================================="""
        result = optimizer.optimize(text)
        
        # Проверяем сохранение важных данных
        assert "ТВ-2024-001" in result.optimized_text
        assert "Телевизор" in result.optimized_text
        assert "3840x2160" in result.optimized_text
        assert "45990.00" in result.optimized_text
        assert "Bluetooth 5.0" in result.optimized_text
        
        # Проверяем удаление шума
        assert "=====" not in result.optimized_text
        assert "Стр." not in result.optimized_text or result.optimized_text.count("Стр.") <= 1
        
        # Проверяем экономию
        assert result.reduction_pct > 15.0  # Ожидаем экономию минимум 15%
        assert result.chars_after < result.chars_before
    
    def test_no_changes_needed(self, optimizer):
        """Тест когда текст уже оптимален"""
        text = "Простой чистый текст без шума"
        result = optimizer.optimize(text)
        # Текст должен остаться практически неизменным
        assert "Простой чистый текст без шума" in result.optimized_text
        assert result.reduction_pct < 5.0  # Минимальные изменения
    
    def test_change_spans_exist(self, optimizer):
        """Тест что change_spans генерируются"""
        text = """Заголовок
===================
Текст"""
        result = optimizer.optimize(text)
        assert len(result.change_spans) > 0
        assert all(hasattr(span, 'start') for span in result.change_spans)
        assert all(hasattr(span, 'end') for span in result.change_spans)
        assert all(hasattr(span, 'reason') for span in result.change_spans)
    
    def test_very_large_text_performance(self, optimizer):
        """Тест производительности на большом тексте"""
        # Генерируем текст ~1MB
        text = ("Строка текста с некоторым содержанием.\n" * 10000)
        text += "===========================\n" * 100
        
        import time
        start = time.time()
        result = optimizer.optimize(text)
        duration = time.time() - start
        
        assert duration < 2.0  # Должно обработаться меньше чем за 2 секунды
        assert result.chars_after < result.chars_before
    
    def test_preserve_numbers_in_headers(self, optimizer):
        """Тест что хедеры с номерами не удаляются как повторяющиеся"""
        text = """1. Раздел первый
Содержание раздела
2. Раздел второй
Содержание раздела
3. Раздел третий
Содержание раздела"""
        result = optimizer.optimize(text)
        # Все разделы должны сохраниться
        assert "1. Раздел первый" in result.optimized_text
        assert "2. Раздел второй" in result.optimized_text
        assert "3. Раздел третий" in result.optimized_text
