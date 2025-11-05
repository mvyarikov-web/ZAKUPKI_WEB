"""WSGI middleware, ограничивающий время обработки запроса.

Если обработка занимает больше timeout секунд, возвращается 504 Gateway Timeout.
Для статических файлов и скачиваний можно задать исключения через skip_paths.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable, Iterable, Tuple, List


StartResponse = Callable[[str, List[Tuple[str, str]], None], None]
WSGIApp = Callable[[dict, StartResponse], Iterable[bytes]]


class TimeoutMiddleware:
    def __init__(self, app: WSGIApp, timeout: int = 30, skip_paths: List[str] | None = None, max_workers: int = 32):
        self.app = app
        self.timeout = int(timeout) if timeout else 30
        self.skip_paths = skip_paths or []
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="req-worker")

    def __call__(self, environ: dict, start_response: StartResponse) -> Iterable[bytes]:
        path = environ.get('PATH_INFO', '') or ''
        for prefix in self.skip_paths:
            if path.startswith(prefix):
                return self.app(environ, start_response)

        status_holder: List[str] = []
        headers_holder: List[List[Tuple[str, str]]] = []

        def _start_response(status: str, headers: List[Tuple[str, str]], exc_info=None):
            status_holder.append(status)
            headers_holder.append(list(headers))
            # Возвращаем write-колбэк, но мы не используем его (собираем тело целиком)
            def _write(_data: bytes):
                return None
            return _write

        def run_downstream():
            body_chunks: List[bytes] = []
            try:
                for chunk in self.app(environ, _start_response):
                    # Накапливаем тело (подходит для JSON/HTML). Для больших отдач можно оптимизировать.
                    body_chunks.append(chunk)
            except Exception as e:  # pragma: no cover
                # Пробрасываем дальше, чтобы наверху отдать 500
                raise e
            return body_chunks

        future = self.executor.submit(run_downstream)
        try:
            chunks = future.result(timeout=self.timeout)
            status = status_holder[0] if status_holder else '200 OK'
            headers = headers_holder[0] if headers_holder else [('Content-Type', 'text/plain; charset=utf-8')]
            start_response(status, headers)
            return chunks
        except FuturesTimeout:
            # Таймаут — формируем 504
            future.cancel()
            start_response('504 Gateway Timeout', [('Content-Type', 'text/plain; charset=utf-8')])
            return [f"Запрос превышает лимит времени {self.timeout} сек. Попробуйте позже.".encode('utf-8')]
        except Exception:
            # Непредвиденная ошибка — 500
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8')])
            return [b"Internal Server Error"]
