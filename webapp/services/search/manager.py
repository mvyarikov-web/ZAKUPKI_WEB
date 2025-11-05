"""Нормализация и применение параметров веб-поиска для Perplexity Sonar.

Модуль инкапсулирует всю логику работы с параметрами поиска:
- нормализацию входных параметров из UI/конфига,
- решение о включении/выключении поиска,
- применение параметров к запросу Chat Completions,
- извлечение факта использования поиска из ответа API.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, List
import re
from urllib.parse import urlparse

ALLOWED_RECENCY = {"day", "week", "month", "year"}
ALLOWED_CONTEXT_SIZE = {"low", "medium", "high"}

# MM/DD/YYYY — допустимы варианты без ведущего нуля
DATE_RE = re.compile(r"^(0?[1-9]|1[0-2])/(0?[1-9]|[12][0-9]|3[01])/[0-9]{4}$")


def _normalize_domain(item: str) -> str:
    """Нормализовать запись домена согласно гайду Perplexity.

    - удаляем схему (http/https), путь, параметры, якоря
    - удаляем конечный слеш
    - приводим к чистому домену, сохраняем возможный префикс '-' (denylist)
    """
    if not item:
        return ""
    s = item.strip()
    deny = s.startswith("-")
    if deny:
        s = s[1:].strip()
    # Если это URL — берём netloc
    parsed = urlparse(s)
    if parsed.netloc:
        s = parsed.netloc
    # Удаляем конечный слеш
    s = s.rstrip("/")
    # Простейшая фильтрация мусора
    if not s or "." not in s:
        return ""
    return ("-" + s) if deny else s


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

    # search_domain_filter — только домены, без схем и путей; максимум 20, без дублей
    sdf = raw.get("search_domain_filter")
    domains: List[str] = []
    if isinstance(sdf, list):
        domains = [str(x) for x in sdf]
    elif isinstance(sdf, str):
        domains = [x for x in sdf.split(",")]
    if domains:
        norm_domains: List[str] = []
        seen = set()
        for d in domains:
            nd = _normalize_domain(d)
            if nd and nd not in seen:
                norm_domains.append(nd)
                seen.add(nd)
            if len(norm_domains) >= 20:
                break
        if norm_domains:
            out["search_domain_filter"] = norm_domains

    # recency (будет удалён, если указаны конкретные даты)
    rec = str(raw.get("search_recency_filter", "")).strip().lower()
    if rec in ALLOWED_RECENCY:
        out["search_recency_filter"] = rec

    # publication date filters — переводим в *_filter согласно документации
    after = raw.get("search_after_date") or raw.get("search_after_date_filter")
    before = raw.get("search_before_date") or raw.get("search_before_date_filter")
    if isinstance(after, str) and DATE_RE.match(after.strip()):
        out["search_after_date_filter"] = after.strip()
    if isinstance(before, str) and DATE_RE.match(before.strip()):
        out["search_before_date_filter"] = before.strip()

    # last_updated_*_filter
    lua = raw.get("last_updated_after") or raw.get("last_updated_after_filter")
    lub = raw.get("last_updated_before") or raw.get("last_updated_before_filter")
    if isinstance(lua, str) and DATE_RE.match(lua.strip()):
        out["last_updated_after_filter"] = lua.strip()
    if isinstance(lub, str) and DATE_RE.match(lub.strip()):
        out["last_updated_before_filter"] = lub.strip()

    # Если присутствуют точные даты публикации — recency очищаем (по гайду нельзя совмещать)
    if ("search_after_date_filter" in out) or ("search_before_date_filter" in out):
        out.pop("search_recency_filter", None)

    # country (при наличии)
    country = raw.get("country")
    if isinstance(country, str) and country.strip():
        out["country"] = country.strip()

    # return_* флаги
    for flag in ("return_images", "return_related_questions", "return_citations"):
        val = raw.get(flag)
        if isinstance(val, bool):
            out[flag] = val

    # web_search_options.search_context_size
    scs = str(raw.get("search_context_size", "")).strip().lower()
    if scs in ALLOWED_CONTEXT_SIZE:
        out["search_context_size"] = scs

    return out or None


def is_search_enabled(model_id: str, params_present: bool) -> bool:
    """Включаем поиск для sonar-моделей, если пользователь его запросил (даже без параметров)."""
    return bool(params_present) and ("sonar" in (model_id or "").lower())


def apply_search_to_request(request_params: Dict[str, Any], params: Optional[Dict[str, Any]]) -> None:
    """Применить параметры поиска к словарю запроса Chat Completions.

    Если params None — ничего не делать (ограничения и disable_search решаются на уровне сервиса).
    
    ВАЖНО: Для OpenAI SDK все кастомные параметры Perplexity должны идти через extra_body,
    иначе SDK перемещает их автоматически и они теряются.
    """
    if params is None:
        return

    # Берём/создаём extra_body для Perplexity-специфичных параметров
    extra_body = dict(request_params.get("extra_body", {}))
    
    # Базовые включатели веб-поиска Perplexity (умный режим)
    extra_body["enable_search_classifier"] = True
    extra_body["search_mode"] = params.get("search_mode", "web")
    extra_body["language_preference"] = params.get("language_preference", "ru")

    # Настройки объёма веб-контента
    scs = params.get("search_context_size", "low")
    extra_body["web_search_options"] = {"search_context_size": scs if scs in ALLOWED_CONTEXT_SIZE else "low"}

    # Прочие фильтры
    keys = (
        "max_results",
        "search_domain_filter",
        "search_recency_filter",
        "search_after_date_filter",
        "search_before_date_filter",
        "last_updated_after_filter",
        "last_updated_before_filter",
        "country",
        "return_images",
        "return_related_questions",
        "return_citations",
    )
    for k in keys:
        if k in params:
            extra_body[k] = params[k]
    
    # Помещаем все параметры поиска в extra_body
    request_params["extra_body"] = extra_body


def extract_search_used(response: Any) -> bool:
    """Понять, использовался ли веб-поиск по ответу Perplexity."""
    try:
        return bool(getattr(response, "search_results", None))
    except Exception:
        return False
