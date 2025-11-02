"""Нормализация и применение параметров веб-поиска для Perplexity Sonar.

Модуль инкапсулирует всю логику работы с параметрами поиска:
- нормализацию входных параметров из UI/конфига,
- решение о включении/выключении поиска,
- применение параметров к запросу Chat Completions,
- извлечение факта использования поиска из ответа API.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

ALLOWED_RECENCY = {"day", "week", "month", "year"}


def normalize_search_params(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Привести параметры поиска к каноническому виду.

    Возвращает None, если вход пуст или все поля пустые.
    """
    if not raw or not isinstance(raw, dict):
        return None

    out: Dict[str, Any] = {}

    # max_results
    try:
        mr = int(raw.get("max_results", 10))
        if mr <= 0:
            mr = 10
        out["max_results"] = mr
    except Exception:
        out["max_results"] = 10

    # search_domain_filter
    sdf = raw.get("search_domain_filter")
    if isinstance(sdf, list):
        out["search_domain_filter"] = [str(x).strip() for x in sdf if str(x).strip()]
    elif isinstance(sdf, str):
        out["search_domain_filter"] = [x.strip() for x in sdf.split(",") if x.strip()]

    # recency
    rec = str(raw.get("search_recency_filter", "")).strip().lower()
    if rec in ALLOWED_RECENCY:
        out["search_recency_filter"] = rec

    # dates
    for k in ("search_after_date", "search_before_date"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()  # формат MM/DD/YYYY ожидается фронтом

    # country
    country = raw.get("country")
    if isinstance(country, str) and country.strip():
        out["country"] = country.strip()

    # max_tokens_per_page
    try:
        mt = int(raw.get("max_tokens_per_page", 1024))
        if mt <= 0:
            mt = 1024
        out["max_tokens_per_page"] = mt
    except Exception:
        pass

    return out or None


def is_search_enabled(model_id: str, params: Optional[Dict[str, Any]]) -> bool:
    """Простое правило: поиском занимаются только sonar-модели с непустыми параметрами."""
    return bool(params) and ("sonar" in (model_id or "").lower())


def apply_search_to_request(request_params: Dict[str, Any], params: Optional[Dict[str, Any]]) -> None:
    """Применить параметры поиска к словарю запроса Chat Completions.

    Если params None — ничего не делать (ограничения и disable_search решаются на уровне сервиса).
    """
    if not params:
        return

    keys = (
        "max_results",
        "search_domain_filter",
        "search_recency_filter",
        "search_after_date",
        "search_before_date",
        "country",
        "max_tokens_per_page",
    )
    for k in keys:
        if k in params:
            request_params[k] = params[k]


def extract_search_used(response: Any) -> bool:
    """Понять, использовался ли веб-поиск по ответу Perplexity."""
    try:
        return bool(getattr(response, "search_results", None))
    except Exception:
        return False
