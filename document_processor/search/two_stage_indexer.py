"""Двухэтапный индексатор: быстрая индексация текста + отложенный OCR."""
from __future__ import annotations
import os
import io
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .indexer import Indexer, HEADER_BAR, DOC_START_MARKER, DOC_END_MARKER


@dataclass
class IndexingStageResult:
    """Результат этапа индексации."""
    stage: int  # 1 или 2
    total_files: int
    processed_files: int
    skipped_files: int
    errors: List[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    index_path: str = ""
    
    @property
    def duration_seconds(self) -> float:
        """Длительность этапа в секундах."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class TwoStageIndexer(Indexer):
    """Двухэтапный индексатор с разделением на текстовые файлы и OCR."""
    
    # Расширения файлов, не требующих OCR (текстовые форматы)
    TEXT_FORMATS = {
        'txt', 'docx', 'doc', 'xlsx', 'xls', 
        'html', 'htm', 'csv', 'tsv', 'xml', 'json'
    }
    
    # Расширения архивов (обрабатываются всегда)
    ARCHIVE_FORMATS = {'zip', 'rar'}
    
    # PDF требует анализа (может быть векторным или сканом)
    PDF_FORMAT = 'pdf'
    
    def __init__(self, *, max_depth: int = 10, archive_depth: int = 0):
        super().__init__(max_depth=max_depth, archive_depth=archive_depth)
        self._stage1_result: Optional[IndexingStageResult] = None
        self._stage2_result: Optional[IndexingStageResult] = None
    
    def create_index_two_stage(
        self, 
        root_folder: str,
        progress_callback: Optional[callable] = None
    ) -> Tuple[IndexingStageResult, Optional[IndexingStageResult]]:
        """
        Создаёт индекс в два этапа.
        
        Этап 1: Быстрая индексация текстовых файлов и векторных PDF.
        Этап 2: OCR сканированных PDF (если есть).
        
        Args:
            root_folder: Корневая папка для индексации
            progress_callback: Функция для отчёта о прогрессе
                               Сигнатура: callback(stage, processed, total, file_name)
        
        Returns:
            Кортеж (stage1_result, stage2_result)
        """
        index_path = os.path.join(root_folder, "_search_index.txt")
        
        # Классифицируем файлы
        self._log.info("Классификация файлов для двухэтапной индексации...")
        text_files, ocr_files = self._classify_files(root_folder)
        
        self._log.info(
            f"Классификация завершена: текстовых={len(text_files)}, "
            f"для OCR={len(ocr_files)}"
        )
        
        # Этап 1: Текстовые файлы
        stage1 = self._run_stage1(
            root_folder, 
            index_path, 
            text_files, 
            progress_callback
        )
        self._stage1_result = stage1
        
        # Этап 2: OCR (если есть файлы)
        stage2 = None
        if ocr_files:
            stage2 = self._run_stage2(
                root_folder,
                index_path,
                ocr_files,
                progress_callback
            )
            self._stage2_result = stage2
        else:
            self._log.info("Этап 2: файлов для OCR нет, пропускаем")
        
        return stage1, stage2
    
    def _classify_files(
        self, 
        root_folder: str
    ) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
        """
        Классифицирует файлы на текстовые и требующие OCR.
        
        Returns:
            (text_files, ocr_files) - списки кортежей (rel_path, abs_path, source)
        """
        text_files = []
        ocr_files = []
        
        for rel_path, abs_path, source in self._iter_sources(root_folder):
            ext = self._get_extension(source)
            
            # Архивы могут содержать что угодно - обрабатываем как текстовые
            # (внутренние файлы классифицируются отдельно)
            if '://' in source:  # Виртуальный файл из архива
                # Определяем по расширению виртуального файла
                if ext in self.TEXT_FORMATS:
                    text_files.append((rel_path, abs_path, source))
                elif ext == self.PDF_FORMAT:
                    # PDF из архива - пока в текстовые, анализ покажет
                    text_files.append((rel_path, abs_path, source))
                else:
                    ocr_files.append((rel_path, abs_path, source))
            else:
                # Обычные файлы
                if ext in self.TEXT_FORMATS:
                    text_files.append((rel_path, abs_path, source))
                elif ext == self.PDF_FORMAT:
                    # PDF требует быстрого анализа: векторный или скан?
                    if self._is_likely_vector_pdf(abs_path):
                        text_files.append((rel_path, abs_path, source))
                    else:
                        ocr_files.append((rel_path, abs_path, source))
                elif ext in self.ARCHIVE_FORMATS:
                    # Архивы обрабатываем в этапе 1
                    text_files.append((rel_path, abs_path, source))
        
        return text_files, ocr_files
    
    def _is_likely_vector_pdf(self, pdf_path: str) -> bool:
        """
        Быстрая эвристика: векторный PDF или скан.
        
        Проверяет первые несколько страниц на наличие текстового слоя.
        """
        try:
            from ..pdf_reader.analyzer import PdfAnalyzer
            analyzer = PdfAnalyzer()
            analysis = analyzer.analyze_pdf(pdf_path)
            return analysis.get('is_vector', False)
        except Exception as e:
            self._log.debug(f"Не удалось проанализировать PDF {pdf_path}: {e}")
            # По умолчанию считаем векторным (оптимистичная эвристика)
            return True
    
    def _run_stage1(
        self,
        root_folder: str,
        index_path: str,
        text_files: List[Tuple[str, str, str]],
        progress_callback: Optional[callable] = None
    ) -> IndexingStageResult:
        """Этап 1: Быстрая индексация текстовых файлов."""
        start_time = datetime.now()
        result = IndexingStageResult(
            stage=1,
            total_files=len(text_files),
            processed_files=0,
            skipped_files=0,
            errors=[],
            start_time=start_time
        )
        
        self._log.info(f"Этап 1: индексация {len(text_files)} текстовых файлов...")
        
        try:
            with io.open(index_path, "w", encoding="utf-8") as out:
                for idx, (rel_path, abs_path, source) in enumerate(text_files, 1):
                    try:
                        # Уведомляем о прогрессе
                        if progress_callback:
                            progress_callback(1, idx, len(text_files), source)
                        
                        # Извлекаем текст
                        text, meta = self._extract_text(abs_path, rel_path, source)
                        self._write_entry(out, rel_path=source, text=text, meta=meta)
                        
                        result.processed_files += 1
                        
                        # Логируем прогресс
                        if idx % 10 == 0 or idx == len(text_files):
                            self._log.info(
                                f"Этап 1: {idx}/{len(text_files)} "
                                f"({int(idx/len(text_files)*100)}%)"
                            )
                    
                    except Exception as e:
                        error_msg = f"Ошибка обработки {source}: {str(e)}"
                        self._log.exception(error_msg)
                        result.errors.append(error_msg)
                        result.skipped_files += 1
            
            result.end_time = datetime.now()
            result.index_path = index_path
            
            self._log.info(
                f"Этап 1 завершён: обработано={result.processed_files}, "
                f"пропущено={result.skipped_files}, "
                f"время={result.duration_seconds:.1f}с"
            )
            
        except Exception as e:
            result.end_time = datetime.now()
            error_msg = f"Критическая ошибка на этапе 1: {str(e)}"
            self._log.exception(error_msg)
            result.errors.append(error_msg)
        
        return result
    
    def _run_stage2(
        self,
        root_folder: str,
        index_path: str,
        ocr_files: List[Tuple[str, str, str]],
        progress_callback: Optional[callable] = None
    ) -> IndexingStageResult:
        """Этап 2: OCR сканированных PDF с дозаписью в индекс."""
        start_time = datetime.now()
        result = IndexingStageResult(
            stage=2,
            total_files=len(ocr_files),
            processed_files=0,
            skipped_files=0,
            errors=[],
            start_time=start_time
        )
        
        self._log.info(f"Этап 2: OCR {len(ocr_files)} сканированных файлов...")
        
        try:
            # Дозапись в существующий индекс
            with io.open(index_path, "a", encoding="utf-8") as out:
                for idx, (rel_path, abs_path, source) in enumerate(ocr_files, 1):
                    try:
                        # Уведомляем о прогрессе
                        if progress_callback:
                            progress_callback(2, idx, len(ocr_files), source)
                        
                        # Извлекаем текст с OCR
                        text, meta = self._extract_text(abs_path, rel_path, source)
                        self._write_entry(out, rel_path=source, text=text, meta=meta)
                        
                        result.processed_files += 1
                        
                        # Логируем прогресс
                        if idx % 5 == 0 or idx == len(ocr_files):
                            self._log.info(
                                f"Этап 2 (OCR): {idx}/{len(ocr_files)} "
                                f"({int(idx/len(ocr_files)*100)}%)"
                            )
                    
                    except Exception as e:
                        error_msg = f"Ошибка OCR {source}: {str(e)}"
                        self._log.exception(error_msg)
                        result.errors.append(error_msg)
                        result.skipped_files += 1
            
            result.end_time = datetime.now()
            result.index_path = index_path
            
            self._log.info(
                f"Этап 2 завершён: обработано={result.processed_files}, "
                f"пропущено={result.skipped_files}, "
                f"время={result.duration_seconds:.1f}с"
            )
            
        except Exception as e:
            result.end_time = datetime.now()
            error_msg = f"Критическая ошибка на этапе 2: {str(e)}"
            self._log.exception(error_msg)
            result.errors.append(error_msg)
        
        finally:
            self._cleanup_temp_paths()
        
        return result
    
    @staticmethod
    def _get_extension(filename: str) -> str:
        """Извлекает расширение файла в нижнем регистре."""
        if '.' in filename:
            return filename.rsplit('.', 1)[-1].lower()
        return ''
