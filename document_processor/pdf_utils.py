import os
import time
from typing import Any, Dict, List, Tuple

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None  # type: ignore

# pypdf is preferred import name; fallback to PyPDF2 if needed
try:
    import pypdf  # type: ignore
except Exception:  # pragma: no cover
    pypdf = None  # type: ignore

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:  # pragma: no cover
    pdfminer_extract_text = None  # type: ignore

try:
    import fitz  # PyMuPDF  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

from flask import make_response, send_file


def _file_stats(path: str) -> Dict[str, Any]:
    try:
        st = os.stat(path)
        return {
            'size': st.st_size,
            'mtime': int(st.st_mtime),
        }
    except Exception:
        return {'size': None, 'mtime': None}


def analyze_pdf(path: str) -> Dict[str, Any]:
    """Быстрый анализ PDF: признаки линейности, шифрования, кол-во страниц.
    Все ошибки глотаются, возвращается best-effort словарь.
    """
    info: Dict[str, Any] = {
        'path': path,
        **_file_stats(path),
        'is_pdf': False,
        'linearized': None,
        'is_encrypted': None,
        'pages': None,
        'producer': None,
    }
    try:
        with open(path, 'rb') as f:
            head = f.read(2048)
            info['is_pdf'] = head.startswith(b'%PDF-')
            # эвристика линейности
            info['linearized'] = b'Linearized' in head
    except Exception:
        pass

    # pypdf: шифрование, страницы, метаданные
    try:
        if pypdf is not None:
            with open(path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                enc = getattr(reader, 'is_encrypted', False)
                info['is_encrypted'] = bool(enc)
                try:
                    if enc:
                        try:
                            reader.decrypt("")
                        except Exception:
                            try:
                                reader.decrypt(None)  # type: ignore[arg-type]
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    info['pages'] = len(reader.pages)
                except Exception:
                    pass
                try:
                    meta = getattr(reader, 'metadata', None)
                    if meta and getattr(meta, 'producer', None):
                        info['producer'] = meta.producer
                except Exception:
                    pass
    except Exception:
        pass

    return info


def extract_text_pdf(path: str, budget_seconds: float = 5.0) -> Dict[str, Any]:
    """Пытается извлечь текст из PDF, ограничивая общий тайм-аут budget_seconds.
    Возвращает dict: {text, used_extractor, elapsed_ms, attempts: [{name, ok, elapsed_ms, error}]}
    """
    start = time.time()
    attempts: List[Dict[str, Any]] = []
    text = ''
    used = 'none'

    def left_time() -> float:
        return budget_seconds - (time.time() - start)

    # 1) pdfplumber
    if text == '' and left_time() > 0 and pdfplumber is not None:
        t0 = time.time()
        ok, err = False, None
        try:
            with pdfplumber.open(path) as pdf:
                parts = []
                for page in pdf.pages:
                    if left_time() <= 0:
                        break
                    t = page.extract_text() or ''
                    if t:
                        parts.append(t)
            if parts:
                text = '\n'.join(parts)
                used = 'pdfplumber'
                ok = True
        except Exception as e:  # pragma: no cover
            err = f'{type(e).__name__}: {e}'
        attempts.append({'name': 'pdfplumber', 'ok': ok, 'elapsed_ms': int((time.time()-t0)*1000), 'error': err})

    # 2) pypdf
    if text == '' and left_time() > 0 and pypdf is not None:
        t0 = time.time()
        ok, err = False, None
        try:
            with open(path, 'rb') as f:
                r = pypdf.PdfReader(f)
                try:
                    if getattr(r, 'is_encrypted', False):
                        try:
                            r.decrypt("")
                        except Exception:
                            try:
                                r.decrypt(None)  # type: ignore[arg-type]
                            except Exception:
                                pass
                except Exception:
                    pass
                parts = []
                for p in r.pages:
                    if left_time() <= 0:
                        break
                    t = p.extract_text() or ''
                    if t:
                        parts.append(t)
            if parts:
                text = '\n'.join(parts)
                used = 'pypdf'
                ok = True
        except Exception as e:  # pragma: no cover
            err = f'{type(e).__name__}: {e}'
        attempts.append({'name': 'pypdf', 'ok': ok, 'elapsed_ms': int((time.time()-t0)*1000), 'error': err})

    # 3) pdfminer.six
    if text == '' and left_time() > 0 and pdfminer_extract_text is not None:
        t0 = time.time()
        ok, err = False, None
        try:
            t = pdfminer_extract_text(path) or ''
            if t.strip():
                text = t
                used = 'pdfminer'
                ok = True
        except Exception as e:  # pragma: no cover
            err = f'{type(e).__name__}: {e}'
        attempts.append({'name': 'pdfminer', 'ok': ok, 'elapsed_ms': int((time.time()-t0)*1000), 'error': err})

    # 4) PyMuPDF
    if text == '' and left_time() > 0 and fitz is not None:
        t0 = time.time()
        ok, err = False, None
        try:
            doc = fitz.open(path)
            parts = []
            for page in doc:
                if left_time() <= 0:
                    break
                t = page.get_text("text") or ''
                if t:
                    parts.append(t)
            if parts:
                text = '\n'.join(parts)
                used = 'pymupdf'
                ok = True
        except Exception as e:  # pragma: no cover
            err = f'{type(e).__name__}: {e}'
        attempts.append({'name': 'pymupdf', 'ok': ok, 'elapsed_ms': int((time.time()-t0)*1000), 'error': err})

    elapsed_ms = int((time.time() - start) * 1000)
    return {
        'text': text,
        'used_extractor': used,
        'elapsed_ms': elapsed_ms,
        'attempts': attempts,
    }


def build_pdf_response(path: str, filename: str, inline: bool = True, enable_range: bool = True):
    """Готовит корректный HTTP-ответ для PDF с поддержкой inline/attachment и Range.
    Возвращает flask.Response.
    """
    # conditional=True включает поддержку Range/ETag/Last-Modified у Werkzeug
    resp = make_response(send_file(path, mimetype='application/pdf', as_attachment=not inline, conditional=enable_range))
    # Content-Disposition с UTF-8
    disp = 'inline' if inline else 'attachment'
    try:
        from urllib.parse import quote as _quote
        fname_enc = _quote(filename, safe='')
        resp.headers['Content-Disposition'] = f"{disp}; filename=\"{filename}\"; filename*=UTF-8''{fname_enc}"
    except Exception:
        resp.headers['Content-Disposition'] = f'{disp}; filename="{filename}"'
    # Явно подсвечиваем, что поддерживаем байтовые диапазоны
    if enable_range and 'Accept-Ranges' not in resp.headers:
        resp.headers['Accept-Ranges'] = 'bytes'
    return resp
