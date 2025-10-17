"""Структуры данных для результатов анализа текста."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class Party:
    """Сторона (заказчик/поставщик)."""
    name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Address:
    """Адрес поставки/исполнения."""
    full_address: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Item:
    """Элемент закупки (позиция, товар, услуга)."""
    name: Optional[str] = None
    okpd2_code: Optional[str] = None
    koz_code: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[str] = None
    price_per_unit: Optional[str] = None
    total_price: Optional[str] = None
    specifications: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Terms:
    """Условия закупки."""
    delivery_terms: Optional[str] = None
    warranty: Optional[str] = None
    installation: Optional[str] = None
    payment_terms: Optional[str] = None
    contract_duration: Optional[str] = None
    other: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Procurement:
    """Основная информация о закупке."""
    title: Optional[str] = None
    number: Optional[str] = None
    ikz: Optional[str] = None
    notice_number: Optional[str] = None
    
    # Даты
    publication_date: Optional[str] = None
    deadline_date: Optional[str] = None
    contract_date: Optional[str] = None
    
    # Цены
    initial_price: Optional[str] = None
    contract_price: Optional[str] = None
    currency: str = "RUB"
    
    # Стороны
    customer: Optional[Party] = None
    supplier: Optional[Party] = None
    
    # Адрес поставки
    delivery_address: Optional[Address] = None
    
    # Позиции закупки
    items: List[Item] = field(default_factory=list)
    
    # Условия
    terms: Optional[Terms] = None
    
    # Дополнительная информация
    description: Optional[str] = None
    requirements: Optional[str] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for k, v in asdict(self).items():
            if isinstance(v, dict):
                result[k] = v
            elif isinstance(v, list):
                result[k] = [item if isinstance(item, dict) else item for item in v]
            else:
                result[k] = v
        return result


@dataclass
class AnalysisResult:
    """Результат анализа документов."""
    procurement: Procurement
    sources: List[str] = field(default_factory=list)
    highlights: Dict[str, List[str]] = field(default_factory=dict)
    analysis_date: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'procurement': self.procurement.to_dict(),
            'sources': self.sources,
            'highlights': self.highlights,
            'analysis_date': self.analysis_date,
            'confidence': self.confidence
        }
