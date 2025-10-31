"""
Сервис для оптимизации текста (удаление технического шума без потери смысла)
"""
import re
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class ChangeSpan:
    """Информация об изменённом участке текста"""
    start: int  # позиция в исходном тексте
    end: int    # позиция в исходном тексте  
    reason: str # описание изменения


@dataclass
class OptimizationResult:
    """Результат оптимизации текста"""
    optimized_text: str
    change_spans: List[ChangeSpan]
    chars_before: int
    chars_after: int
    reduction_pct: float


class TextOptimizer:
    """Оптимизатор текста с сохранением смысла"""
    
    def __init__(self):
        # Компилируем регулярные выражения для производительности
        self.patterns = {
            'decorative_lines': re.compile(r'^[\s]*[=\-_#*•│─]{5,}[\s]*$', re.MULTILINE),
            'page_numbers': re.compile(r'(?:Стр\.?|Page|стр\.?)\s*\d+\s*(?:из|of|\/)\s*\d+', re.IGNORECASE),
            'hyphen_breaks': re.compile(r'(\w+)-\s*\n\s*(\w+)'),
            'multiple_spaces': re.compile(r' {2,}'),
            'multiple_newlines': re.compile(r'\n{3,}'),
            'long_dash': re.compile(r'[—–]'),
            'nbsp': re.compile(r'\u00a0'),
            'bullet_points': re.compile(r'^[\s]*[•*\-–]\s+', re.MULTILINE),
            # Паттерн для обнаружения битого текста (кракозябры из-за неправильной кодировки)
            # Ищем специфические символы mojibake, которые НЕ являются нормальной кириллицей
            'mojibake': re.compile(r'[–∂—ë–a—ã–μ–æ–ø–μ—Ä–∞—Ü–∏–∏—Ç–æ–a—å–∫–æ–Ω–∞—ç—Ç–∞–ø–μ–∏–Ω–¥–μ–∫—Å–∞—Ü–∏–∏–Ω–μ–≤–ú–∏–Ω–∏–o–∞–a—å–Ω—ã–μ–∏–∑–o–μ–Ω–μ–Ω–∏—è–ü—É–±–a–∏—á–Ω—ã]{8,}'),
            # Строки с высокой плотностью специфических символов битого текста (минимум 8 подряд)
            'garbage_line': re.compile(r'[–]{2,}[∂—ë]+[–]{2,}|[–∂—ë–a—ã–μ–æ–ø]{10,}', re.MULTILINE),
        }
    
    def optimize(self, text: str) -> OptimizationResult:
        """
        Оптимизирует текст по правилам без потери смысла
        
        Args:
            text: Исходный текст
            
        Returns:
            OptimizationResult с оптимизированным текстом и метриками
        """
        if not text or not text.strip():
            return OptimizationResult(
                optimized_text='',
                change_spans=[],
                chars_before=0,
                chars_after=0,
                reduction_pct=0.0
            )
        
        # Сначала применяем базовую нормализацию (не считается оптимизацией)
        text, _ = self._normalize_whitespace(text)
        
        # Теперь считаем исходный размер ПОСЛЕ нормализации
        original_text = text
        chars_before = len(text)
        change_spans: List[ChangeSpan] = []
        
        # Применяем правила оптимизации последовательно
        
        text, spans2 = self._remove_decorative_noise(text, original_text)
        change_spans.extend(spans2)
        
        text, spans3 = self._fix_hyphen_breaks(text, original_text)
        change_spans.extend(spans3)
        
        text, spans4 = self._remove_repeated_headers(text, original_text)
        change_spans.extend(spans4)
        
        text, spans5 = self._normalize_punctuation(text, original_text)
        change_spans.extend(spans5)
        
        text, spans6 = self._unify_lists(text, original_text)
        change_spans.extend(spans6)
        
        chars_after = len(text)
        reduction_pct = ((chars_before - chars_after) / chars_before * 100) if chars_before > 0 else 0.0
        
        return OptimizationResult(
            optimized_text=text,
            change_spans=sorted(change_spans, key=lambda x: x.start),
            chars_before=chars_before,
            chars_after=chars_after,
            reduction_pct=round(reduction_pct, 2)
        )
    
    def _normalize_whitespace(self, text: str) -> Tuple[str, List[ChangeSpan]]:
        """Нормализация пробелов и переводов строк"""
        spans = []
        
        # \r\n → \n
        text = text.replace('\r\n', '\n')
        
        # Удаление невидимых управляющих символов (кроме \n, \t)
        control_chars = ''.join(chr(i) for i in range(32) if i not in (9, 10))
        for char in control_chars:
            if char in text:
                text = text.replace(char, '')
        
        # Схлопывание множественных пробелов
        text = self.patterns['multiple_spaces'].sub(' ', text)
        
        # Схлопывание пустых строк (max 2 подряд)
        text = self.patterns['multiple_newlines'].sub('\n\n', text)
        
        return text, spans
    
    def _remove_decorative_noise(self, text: str, original: str) -> Tuple[str, List[ChangeSpan]]:
        """Удаление декоративных линий и служебных вставок"""
        spans = []
        lines = text.split('\n')
        new_lines = []
        pos = 0
        
        for line in lines:
            line_len = len(line) + 1  # +1 for \n
            
            # Проверяем декоративные линии
            if self.patterns['decorative_lines'].match(line):
                spans.append(ChangeSpan(
                    start=pos,
                    end=pos + line_len,
                    reason="Удалена декоративная линия"
                ))
            # Проверяем номера страниц
            elif self.patterns['page_numbers'].search(line):
                spans.append(ChangeSpan(
                    start=pos,
                    end=pos + line_len,
                    reason="Удалён номер страницы"
                ))
            # Проверяем битый текст (кракозябры)
            elif self.patterns['mojibake'].search(line):
                spans.append(ChangeSpan(
                    start=pos,
                    end=pos + line_len,
                    reason="Удалена строка с битым текстом (неправильная кодировка)"
                ))
            # Проверяем строки с высокой плотностью мусорных символов
            elif self.patterns['garbage_line'].search(line):
                spans.append(ChangeSpan(
                    start=pos,
                    end=pos + line_len,
                    reason="Удалена строка с нечитаемыми символами"
                ))
            else:
                new_lines.append(line)
            
            pos += line_len
        
        return '\n'.join(new_lines), spans
    
    def _fix_hyphen_breaks(self, text: str, original: str) -> Tuple[str, List[ChangeSpan]]:
        """Склейка дефисных переносов слов"""
        spans = []
        
        def replacer(match):
            # Проверяем, что это не составное слово (бизнес-план и т.п.)
            before = match.group(1)
            after = match.group(2)
            
            # Если обе части русские или латинские буквы - склеиваем
            if (before.isalpha() and after.isalpha()):
                return before + after
            return match.group(0)
        
        new_text = self.patterns['hyphen_breaks'].sub(replacer, text)
        
        # Если текст изменился, добавляем общий span
        if new_text != text:
            spans.append(ChangeSpan(
                start=0,
                end=len(text),
                reason="Склеены дефисные переносы слов"
            ))
        
        return new_text, spans
    
    def _remove_repeated_headers(self, text: str, original: str) -> Tuple[str, List[ChangeSpan]]:
        """Удаление повторяющихся хедеров/футеров"""
        spans = []
        lines = text.split('\n')
        
        # Подсчитываем повторения коротких строк
        line_counts = {}
        for line in lines:
            stripped = line.strip()
            if len(stripped) <= 100 and stripped:
                # Исключаем строки с числами/датами/артикулами
                if not re.search(r'\d{2,}|[А-Я]{2,}-\d+|\d+\.\d+', stripped):
                    line_counts[stripped] = line_counts.get(stripped, 0) + 1
        
        # Находим часто повторяющиеся строки (≥3 раза)
        repeated = {line for line, count in line_counts.items() if count >= 3}
        
        if not repeated:
            return text, spans
        
        # Удаляем повторы, оставляя только первое вхождение
        seen = set()
        new_lines = []
        pos = 0
        
        for line in lines:
            line_len = len(line) + 1
            stripped = line.strip()
            
            if stripped in repeated:
                if stripped not in seen:
                    seen.add(stripped)
                    new_lines.append(line)
                else:
                    spans.append(ChangeSpan(
                        start=pos,
                        end=pos + line_len,
                        reason="Удалён повторяющийся хедер/футер"
                    ))
            else:
                new_lines.append(line)
            
            pos += line_len
        
        return '\n'.join(new_lines), spans
    
    def _normalize_punctuation(self, text: str, original: str) -> Tuple[str, List[ChangeSpan]]:
        """Нормализация пунктуации"""
        spans = []
        
        # Длинное тире → короткое
        text = self.patterns['long_dash'].sub('-', text)
        
        # NBSP → обычный пробел
        text = self.patterns['nbsp'].sub(' ', text)
        
        # Множественные знаки препинания
        text = re.sub(r'\.{4,}', '...', text)
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        
        return text, spans
    
    def _unify_lists(self, text: str, original: str) -> Tuple[str, List[ChangeSpan]]:
        """Унификация маркеров списков"""
        spans = []
        
        # Заменяем различные маркеры на стандартный "- "
        text = self.patterns['bullet_points'].sub('- ', text)
        
        return text, spans


def get_text_optimizer() -> TextOptimizer:
    """Фабрика для получения экземпляра оптимизатора"""
    return TextOptimizer()
