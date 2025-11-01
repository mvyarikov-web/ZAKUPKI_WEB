"""
Клиент для Perplexity Search API
Документация: https://docs.perplexity.ai/reference/post_search
"""
import os
import json
import requests
from dataclasses import dataclass
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Результат поиска от Perplexity Search API"""
    title: str
    url: str
    snippet: str
    date: Optional[str] = None
    last_updated: Optional[str] = None


class PerplexitySearchClient:
    """Клиент для работы с Perplexity Search API"""
    
    API_URL = "https://api.perplexity.ai/search"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация клиента
        
        Args:
            api_key: API ключ Perplexity. Если не указан, берётся из переменной окружения
        """
        self.api_key = api_key or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("Perplexity API key не найден. Укажите через параметр или PERPLEXITY_API_KEY")
    
    def verify_key(self) -> bool:
        """
        Проверка валидности API ключа
        
        Returns:
            True если ключ валиден, False иначе
        """
        try:
            # Минимальный тестовый запрос
            self.search(query="test", max_results=1)
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки ключа Perplexity Search API: {e}")
            return False
    
    def search(
        self,
        query: Union[str, List[str]],
        *,
        max_results: int = 10,
        search_domain_filter: Optional[List[str]] = None,
        search_recency_filter: Optional[str] = None,
        search_after_date: Optional[str] = None,
        search_before_date: Optional[str] = None,
        country: Optional[str] = None,
        max_tokens_per_page: int = 1024,
        timeout_s: int = 30
    ) -> List[SearchResult]:
        """
        Выполнить поиск через Perplexity Search API
        
        Args:
            query: Поисковый запрос (строка) или список запросов (multi-query)
            max_results: Максимальное количество результатов (1-20), по умолчанию 10
            search_domain_filter: Список доменов/URL для фильтрации (до 20). 
                                  Префикс '-' исключает домен
            search_recency_filter: Фильтр свежести: "day", "week", "month", "year"
            search_after_date: Фильтр по дате публикации "после" (формат MM/DD/YYYY)
            search_before_date: Фильтр по дате публикации "до" (формат MM/DD/YYYY)
            country: ISO-код страны для геофильтрации (например, "RU", "US")
            max_tokens_per_page: Максимум токенов текста с каждой страницы (по умолчанию 1024)
            timeout_s: Таймаут запроса в секундах
            
        Returns:
            Список SearchResult с результатами поиска
            
        Raises:
            requests.HTTPError: При ошибках API
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        body = {
            "query": query,
            "max_results": max_results,
            "max_tokens_per_page": max_tokens_per_page,
        }
        
        # Добавляем опциональные параметры
        if search_domain_filter:
            body["search_domain_filter"] = search_domain_filter
        if search_recency_filter:
            body["search_recency_filter"] = search_recency_filter
        if search_after_date:
            body["search_after_date"] = search_after_date
        if search_before_date:
            body["search_before_date"] = search_before_date
        if country:
            body["country"] = country
        
        logger.info(f"Perplexity Search API запрос: query={query}, max_results={max_results}")
        
        try:
            response = requests.post(
                self.API_URL,
                headers=headers,
                data=json.dumps(body),
                timeout=timeout_s
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for item in data.get("results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    date=item.get("date"),
                    last_updated=item.get("last_updated")
                ))
            
            logger.info(f"Perplexity Search API вернул {len(results)} результатов")
            return results
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Perplexity Search API: Неверный API ключ (401)")
                raise ValueError("Неверный API ключ Perplexity")
            elif e.response.status_code == 429:
                logger.error("Perplexity Search API: Превышен лимит запросов (429)")
                raise ValueError("Превышен лимит запросов Perplexity Search API")
            else:
                logger.error(f"Perplexity Search API ошибка {e.response.status_code}: {e.response.text}")
                raise
        except requests.exceptions.Timeout:
            logger.error(f"Perplexity Search API: Таймаут после {timeout_s}с")
            raise TimeoutError(f"Таймаут запроса к Perplexity Search API ({timeout_s}с)")
        except Exception as e:
            logger.error(f"Perplexity Search API непредвиденная ошибка: {e}")
            raise


def example_usage():
    """Примеры использования"""
    client = PerplexitySearchClient()
    
    # Пример 1: Простой поиск
    results = client.search("сплит-система Gree Pular характеристики 2025", max_results=5)
    for r in results:
        print(f"Заголовок: {r.title}")
        print(f"URL: {r.url}")
        print(f"Сниппет: {r.snippet[:100]}...")
        print()
    
    # Пример 2: Multi-query
    results = client.search([
        "Gree Pular GWH09AGAXA характеристики",
        "цена Gree Pular 09 Россия 2025",
    ], max_results=10)
    
    # Пример 3: Поиск по закупкам с фильтрами
    results = client.search(
        "требования к монтажу кондиционеров",
        search_domain_filter=["zakupki.gov.ru", "tenderplan.ru"],
        search_recency_filter="month",
        max_results=10
    )
    
    # Пример 4: Поиск по датам
    results = client.search(
        "изменения СП кондиционирование",
        search_after_date="09/01/2025",
        search_before_date="10/31/2025",
        max_results=10
    )


if __name__ == "__main__":
    example_usage()
