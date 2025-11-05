"""Модуль извлечения структурированных данных из сводного индекса."""
import re
import os
import logging
from typing import List, Dict, Any, Optional
from document_processor.analysis.schemas import (
    Procurement, Item, Party, Address, Terms, AnalysisResult
)


class Extractor:
    """Извлекает структурированные данные из сводного индекса _search_index.txt."""
    
    def __init__(self, use_spacy: bool = True):
        """
        Инициализация экстрактора.
        
        Args:
            use_spacy: Использовать ли spaCy для NLP (если доступен)
        """
        self.logger = logging.getLogger(__name__)
        self.nlp = None
        
        # Пытаемся загрузить spaCy, если запрошено
        if use_spacy:
            try:
                import spacy
                try:
                    self.nlp = spacy.load('ru_core_news_sm')
                    self.logger.info('spaCy ru_core_news_sm загружен успешно')
                except OSError:
                    self.logger.info('spaCy модель ru_core_news_sm не установлена, используем только regex')
            except ImportError:
                self.logger.info('spaCy не установлен, используем только regex')
    
    def analyze_index(self, index_path: str) -> AnalysisResult:
        """
        Анализирует сводный индекс и извлекает структурированные данные.
        
        Args:
            index_path: Путь к файлу _search_index.txt
            
        Returns:
            AnalysisResult с извлечёнными данными
        """
        if not os.path.exists(index_path):
            raise FileNotFoundError(f'Индекс не найден: {index_path}')
        
        # Читаем весь индекс
        with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Парсим документы из индекса
        documents = self._parse_documents(content)
        
        # Объединяем весь текст документов для анализа
        full_text = '\n\n'.join(doc['body'] for doc in documents)
        sources = [doc['title'] for doc in documents]
        
        # Извлекаем данные
        procurement = self._extract_procurement_data(full_text, documents)
        highlights = self._extract_highlights(full_text)
        confidence = self._calculate_confidence(procurement)
        
        return AnalysisResult(
            procurement=procurement,
            sources=sources,
            highlights=highlights,
            confidence=confidence
        )
    
    def _parse_documents(self, content: str) -> List[Dict[str, Any]]:
        """
        Парсит индекс на отдельные документы, игнорируя заголовки.
        
        Args:
            content: Содержимое индексного файла
            
        Returns:
            Список документов с метаданными
        """
        documents = []
        
        # Используем более надёжный способ: ищем блоки между маркерами
        doc_pattern = re.compile(
            r'ЗАГОЛОВОК:\s*([^\n]+).*?'
            r'<<< НАЧАЛО ДОКУМЕНТА >>>\s*'
            r'(.*?)'
            r'<<< КОНЕЦ ДОКУМЕНТА >>>',
            re.DOTALL
        )
        
        for match in doc_pattern.finditer(content):
            title = match.group(1).strip()
            body = match.group(2).strip()
            
            if title and body:
                documents.append({
                    'title': title,
                    'format': None,
                    'source': None,
                    'body': body
                })
        
        self.logger.info(f'Распознано документов: {len(documents)}')
        return documents
    
    def _extract_procurement_data(self, text: str, documents: List[Dict]) -> Procurement:
        """
        Извлекает данные о закупке из текста.
        
        Args:
            text: Полный текст для анализа
            documents: Список документов с метаданными
            
        Returns:
            Объект Procurement с извлечёнными данными
        """
        procurement = Procurement()
        
        # Извлекаем название/предмет закупки
        procurement.title = self._extract_title(text)
        
        # Извлекаем номера и идентификаторы
        procurement.number = self._extract_number(text)
        procurement.ikz = self._extract_ikz(text)
        procurement.notice_number = self._extract_notice_number(text)
        
        # Извлекаем даты
        dates = self._extract_dates(text)
        procurement.publication_date = dates.get('publication')
        procurement.deadline_date = dates.get('deadline')
        procurement.contract_date = dates.get('contract')
        
        # Извлекаем цены
        prices = self._extract_prices(text)
        procurement.initial_price = prices.get('initial')
        procurement.contract_price = prices.get('contract')
        
        # Извлекаем стороны
        procurement.customer = self._extract_customer(text)
        procurement.supplier = self._extract_supplier(text)
        
        # Извлекаем адрес поставки
        procurement.delivery_address = self._extract_delivery_address(text)
        
        # Извлекаем позиции закупки
        procurement.items = self._extract_items(text)
        
        # Извлекаем условия
        procurement.terms = self._extract_terms(text)
        
        # Извлекаем описание и требования
        procurement.description = self._extract_description(text)
        procurement.requirements = self._extract_requirements(text)
        
        return procurement
    
    def _extract_title(self, text: str) -> Optional[str]:
        """Извлекает название/предмет закупки."""
        patterns = [
            r'(?:предмет\s+контракта|предмет\s+закупки|наименование)[\s:]+(.{10,200})',
            r'(?:на\s+поставку|на\s+оказание\s+услуг|на\s+выполнение\s+работ)[\s:]+(.{10,200})',
            r'(?:договор|контракт)[\s№\d]*[\s:]+(.{10,200})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                title = match.group(1).strip()
                # Обрезаем на первом переводе строки или точке
                title = re.split(r'[\n\.]', title)[0].strip()
                if len(title) > 10:
                    return title
        
        return None
    
    def _extract_number(self, text: str) -> Optional[str]:
        """Извлекает номер закупки/контракта."""
        patterns = [
            r'(?:номер\s+извещения|№\s*извещения)[\s:№]*(\d+[-/\d]*)',
            r'(?:номер\s+закупки|№\s*закупки)[\s:№]*(\d+[-/\d]*)',
            r'(?:реестровый\s+номер|номер\s+в\s+реестре)[\s:№]*(\d+[-/\d]*)',
            r'№\s*(\d{4,}[-/\d]*)',  # Более гибкий паттерн для номеров
            r'закупки\s+№\s*(\d+[-/\d]*)',
            r'извещение.*?№\s*(\d+[-/\d]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_ikz(self, text: str) -> Optional[str]:
        """Извлекает ИКЗ (идентификационный код закупки)."""
        # ИКЗ обычно 36 цифр
        match = re.search(r'(?:ИКЗ|идентификационный\s+код)[\s:№]*(\d{20,36})', text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    
    def _extract_notice_number(self, text: str) -> Optional[str]:
        """Извлекает номер извещения."""
        match = re.search(r'извещение\s*№?\s*(\d+[-/\d]*)', text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    
    def _extract_dates(self, text: str) -> Dict[str, Optional[str]]:
        """Извлекает даты из текста."""
        dates = {
            'publication': None,
            'deadline': None,
            'contract': None
        }
        
        # Паттерн для дат в различных форматах
        date_pattern = r'(\d{1,2}[-./]\d{1,2}[-./]\d{2,4}|\d{2,4}[-./]\d{1,2}[-./]\d{1,2})'
        
        # Дата публикации
        pub_match = re.search(r'(?:дата\s+размещения|дата\s+публикации|опубликовано)[\s:]*' + date_pattern, 
                             text, re.IGNORECASE)
        if pub_match:
            dates['publication'] = pub_match.group(1)
        
        # Дата окончания приема заявок
        deadline_match = re.search(r'(?:окончани[еяю]\s+подачи\s+заявок|срок\s+подачи)[\s:]*' + date_pattern,
                                  text, re.IGNORECASE)
        if deadline_match:
            dates['deadline'] = deadline_match.group(1)
        
        # Дата контракта
        contract_match = re.search(r'(?:дата\s+контракта|дата\s+договора|заключен)[\s:]*' + date_pattern,
                                  text, re.IGNORECASE)
        if contract_match:
            dates['contract'] = contract_match.group(1)
        
        return dates
    
    def _extract_prices(self, text: str) -> Dict[str, Optional[str]]:
        """Извлекает цены из текста."""
        prices = {
            'initial': None,
            'contract': None
        }
        
        # Паттерн для цен (число с возможными пробелами, запятыми, точками)
        price_pattern = r'([\d\s]+(?:[.,]\d{2})?)\s*(?:руб|₽|RUB)'
        
        # Начальная (максимальная) цена - расширенные паттерны
        initial_patterns = [
            r'(?:начальная\s+цена(?:\s+контракта)?)[\s:]*' + price_pattern,
            r'(?:максимальная\s+цена)[\s:]*' + price_pattern,
            r'(?:НМЦК)[\s:]*' + price_pattern,
        ]
        
        for pattern in initial_patterns:
            initial_match = re.search(pattern, text, re.IGNORECASE)
            if initial_match:
                prices['initial'] = initial_match.group(1).strip()
                break
        
        # Цена контракта
        contract_match = re.search(
            r'(?:цена\s+контракта|цена\s+договора|сумма\s+контракта)[\s:]*' + price_pattern,
            text, re.IGNORECASE
        )
        if contract_match:
            prices['contract'] = contract_match.group(1).strip()
        
        return prices
    
    def _extract_customer(self, text: str) -> Optional[Party]:
        """Извлекает данные заказчика."""
        customer = Party()
        
        # Ищем название организации заказчика
        org_patterns = [
            r'(?:заказчик|организатор)[\s:]+([А-ЯЁ][^.\n]{10,150})',
            r'(?:наименование\s+заказчика)[\s:]+([А-ЯЁ][^.\n]{10,150})',
        ]
        
        for pattern in org_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Обрезаем на переводе строки или точке
                name = re.split(r'[\n]', name)[0].strip()
                if len(name) > 10:
                    customer.name = name
                    break
        
        # ИНН заказчика
        inn_match = re.search(r'(?:ИНН\s+заказчика|заказчик.*ИНН)[\s:]*(\d{10,12})', text, re.IGNORECASE)
        if inn_match:
            customer.inn = inn_match.group(1)
        
        # КПП заказчика
        kpp_match = re.search(r'(?:КПП\s+заказчика|заказчик.*КПП)[\s:]*(\d{9})', text, re.IGNORECASE)
        if kpp_match:
            customer.kpp = kpp_match.group(1)
        
        # Используем spaCy для дополнительного извлечения, если доступен
        if self.nlp and not customer.name:
            doc = self.nlp(text[:5000])  # Анализируем первые 5000 символов
            for ent in doc.ents:
                if ent.label_ == 'ORG':
                    customer.name = ent.text
                    break
        
        return customer if customer.name or customer.inn else None
    
    def _extract_supplier(self, text: str) -> Optional[Party]:
        """Извлекает данные поставщика."""
        supplier = Party()
        
        # Ищем название организации поставщика
        org_patterns = [
            r'(?:поставщик|исполнитель|подрядчик)[\s:]+([А-ЯЁ][^.\n]{10,150})',
            r'(?:победитель)[\s:]+([А-ЯЁ][^.\n]{10,150})',
        ]
        
        for pattern in org_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                name = re.split(r'[\n]', name)[0].strip()
                if len(name) > 10:
                    supplier.name = name
                    break
        
        # ИНН поставщика
        inn_match = re.search(r'(?:ИНН\s+поставщика|поставщик.*ИНН)[\s:]*(\d{10,12})', text, re.IGNORECASE)
        if inn_match:
            supplier.inn = inn_match.group(1)
        
        return supplier if supplier.name or supplier.inn else None
    
    def _extract_delivery_address(self, text: str) -> Optional[Address]:
        """Извлекает адрес поставки."""
        address = Address()
        
        # Ищем полный адрес
        addr_patterns = [
            r'(?:место\s+поставки|адрес\s+поставки|место\s+доставки)[\s:]+(.{20,200})',
            r'(?:адрес\s+объекта|место\s+выполнения)[\s:]+(.{20,200})',
        ]
        
        for pattern in addr_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                addr_text = match.group(1).strip()
                addr_text = re.split(r'[\n]', addr_text)[0].strip()
                if len(addr_text) > 10:
                    address.full_address = addr_text
                    break
        
        # Извлекаем компоненты адреса, если spaCy доступен
        if self.nlp and address.full_address:
            doc = self.nlp(address.full_address)
            for ent in doc.ents:
                if ent.label_ == 'LOC':
                    if not address.city:
                        address.city = ent.text
        
        # Простое извлечение города через regex
        if not address.city:
            city_match = re.search(r'(?:г\.|город)\s*([А-ЯЁ][а-яё-]+)', address.full_address or text, re.IGNORECASE)
            if city_match:
                address.city = city_match.group(1)
        
        return address if address.full_address else None
    
    def _extract_items(self, text: str) -> List[Item]:
        """Извлекает позиции закупки."""
        items = []
        
        # Ищем секции с позициями/товарами
        # Паттерны для ОКПД2 (включая завершающие цифры)
        okpd_pattern = r'(?:ОКПД[-\s]?2?|код\s+ОКПД)[\s:]*(\d{2}(?:\.\d{2,3}){0,4})'
        okpd_matches = re.finditer(okpd_pattern, text, re.IGNORECASE)
        
        for match in okpd_matches:
            item = Item()
            item.okpd2_code = match.group(1)
            
            # Контекст вокруг кода для извлечения названия
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 200)
            context = text[start:end]
            
            # Название товара (обычно перед или после кода)
            name_match = re.search(r'([А-ЯЁ][^.\n]{10,100})', context)
            if name_match:
                item.name = name_match.group(1).strip()
            
            # Единица измерения
            unit_match = re.search(r'(?:единица|ед\.|шт|штук|л|литр|кг|тонн|м|метр|компл)', 
                                  context, re.IGNORECASE)
            if unit_match:
                item.unit = unit_match.group(0)
            
            # Количество
            qty_match = re.search(r'(?:количество|кол-во)[\s:]*(\d+[.,]?\d*)', context, re.IGNORECASE)
            if qty_match:
                item.quantity = qty_match.group(1)
            
            items.append(item)
        
        # Ограничиваем количество позиций для производительности
        return items[:20]
    
    def _extract_terms(self, text: str) -> Optional[Terms]:
        """Извлекает условия закупки."""
        terms = Terms()
        
        # Условия доставки
        delivery_match = re.search(
            r'(?:условия\s+доставки|срок\s+поставки)[\s:]+(.{10,150})',
            text, re.IGNORECASE
        )
        if delivery_match:
            terms.delivery_terms = delivery_match.group(1).strip()
        
        # Гарантия
        warranty_match = re.search(
            r'(?:гарантия|гарантийный\s+срок)[\s:]+(.{5,100})',
            text, re.IGNORECASE
        )
        if warranty_match:
            terms.warranty = warranty_match.group(1).strip()
        
        # Монтаж
        install_match = re.search(
            r'(?:монтаж|установка|шефмонтаж)[\s:]+(.{5,100})',
            text, re.IGNORECASE
        )
        if install_match:
            terms.installation = install_match.group(1).strip()
        
        # Условия оплаты
        payment_match = re.search(
            r'(?:условия\s+оплаты|порядок\s+оплаты)[\s:]+(.{10,150})',
            text, re.IGNORECASE
        )
        if payment_match:
            terms.payment_terms = payment_match.group(1).strip()
        
        return terms if any([terms.delivery_terms, terms.warranty, 
                           terms.installation, terms.payment_terms]) else None
    
    def _extract_description(self, text: str) -> Optional[str]:
        """Извлекает описание предмета закупки."""
        desc_match = re.search(
            r'(?:описание|характеристик[иа])[\s:]+(.{20,500})',
            text, re.IGNORECASE | re.DOTALL
        )
        if desc_match:
            desc = desc_match.group(1).strip()
            # Обрезаем на первых нескольких строках
            lines = desc.split('\n')[:5]
            return '\n'.join(lines)
        return None
    
    def _extract_requirements(self, text: str) -> Optional[str]:
        """Извлекает требования к закупке."""
        req_match = re.search(
            r'(?:требования|технические\s+требования|ТЗ)[\s:]+(.{20,500})',
            text, re.IGNORECASE | re.DOTALL
        )
        if req_match:
            req = req_match.group(1).strip()
            lines = req.split('\n')[:5]
            return '\n'.join(lines)
        return None
    
    def _extract_highlights(self, text: str) -> Dict[str, List[str]]:
        """
        Извлекает ключевые фрагменты для подсветки в UI.
        
        Returns:
            Словарь {поле: [список фрагментов]}
        """
        highlights = {}
        
        # Примеры фрагментов для разных полей
        fields_patterns = {
            'title': [r'(?:предмет\s+контракта|предмет\s+закупки)[\s:]+(.{10,100})'],
            'number': [r'(?:номер\s+извещения|№\s*извещения)[\s:№]*(\d+[-/\d]*)'],
            'prices': [r'(?:начальная\s+цена|НМЦК)[\s:]*([\d\s]+(?:[.,]\d{2})?\s*(?:руб|₽))'],
            'dates': [r'(?:дата\s+размещения|дата\s+публикации)[\s:]*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})'],
        }
        
        for field, patterns in fields_patterns.items():
            highlights[field] = []
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Контекст вокруг найденного
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    snippet = text[start:end].strip()
                    highlights[field].append(snippet)
                    if len(highlights[field]) >= 3:  # Максимум 3 примера
                        break
        
        return highlights
    
    def _calculate_confidence(self, procurement: Procurement) -> Dict[str, float]:
        """
        Вычисляет уровень уверенности для извлечённых полей.
        
        Returns:
            Словарь {поле: уверенность от 0 до 1}
        """
        confidence = {}
        
        # Простая эвристика: наличие поля = высокая уверенность
        fields_to_check = {
            'title': procurement.title,
            'number': procurement.number,
            'ikz': procurement.ikz,
            'customer': procurement.customer,
            'prices': procurement.initial_price or procurement.contract_price,
            'items': len(procurement.items) > 0,
        }
        
        for field, value in fields_to_check.items():
            if value:
                # Базовая уверенность при наличии значения
                confidence[field] = 0.8
                
                # Для числовых полей (ИКЗ, номера) - выше уверенность
                if field in ['ikz', 'number'] and isinstance(value, str) and len(value) > 5:
                    confidence[field] = 0.9
            else:
                confidence[field] = 0.0
        
        return confidence
