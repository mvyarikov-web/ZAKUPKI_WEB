"""Анализатор PDF-документов (перенесено из pdf_utils.py)."""
import os
from typing import Any, Dict

try:
    import pypdf  # type: ignore
except Exception:  # pragma: no cover
    pypdf = None  # type: ignore


class PdfAnalyzer:
    """Быстрый анализ PDF-документов без извлечения текста."""
    
    def analyze_pdf(self, path: str) -> Dict[str, Any]:
        """Быстрый анализ PDF: признаки линейности, шифрования, кол-во страниц.
        Все ошибки глотаются, возвращается best-effort словарь.
        
        Args:
            path: Путь к PDF-файлу
            
        Returns:
            Dict с полями: is_pdf, linearized, is_encrypted, pages, producer, size, mtime
        """
        info: Dict[str, Any] = {
            'path': path,
            **self._file_stats(path),
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
    
    def _file_stats(self, path: str) -> Dict[str, Any]:
        """Получить размер и время модификации файла."""
        try:
            st = os.stat(path)
            return {
                'size': st.st_size,
                'mtime': int(st.st_mtime),
            }
        except Exception:
            return {'size': None, 'mtime': None}
