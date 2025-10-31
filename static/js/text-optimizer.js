// Text Optimization Module
(function() {
    'use strict';

    // Элементы DOM
    const btnOptimizeText = document.getElementById('btn-optimize-text');
    const modalOptimizePreview = document.getElementById('modal-optimize-preview');
    const optimizePreviewClose = document.getElementById('optimize-preview-close');
    const btnCancelOptimization = document.getElementById('btn-cancel-optimization');
    const btnApplyOptimization = document.getElementById('btn-apply-optimization');
    const optimizeMetrics = document.getElementById('optimize-metrics');
    const optimizeTextPreview = document.getElementById('optimize-text-preview');
    
    // Получаем элементы для текста из RAG модалки
    const ragPromptText = document.getElementById('ragPromptText');
    const ragDocumentsText = document.getElementById('ragDocumentsText');
    
    // Состояние
    let optimizationResult = null;
    
    // Открытие модалки оптимизации
    if (btnOptimizeText) {
        btnOptimizeText.addEventListener('click', async function() {
            // Собираем текст для оптимизации
            const promptText = ragPromptText ? ragPromptText.value : '';
            const docsText = ragDocumentsText ? ragDocumentsText.value : '';
            const fullText = `${promptText}\n\n${docsText}`.trim();
            
            if (!fullText) {
                showMessage('Нет текста для оптимизации', 'error');
                return;
            }
            
            // Показываем модалку с загрузкой
            modalOptimizePreview.style.display = 'block';
            optimizeMetrics.textContent = 'Анализ текста...';
            optimizeTextPreview.textContent = 'Подождите, выполняется оптимизация...';
            
            try {
                // Отправляем запрос на оптимизацию
                const response = await fetch('/ai_analysis/optimize/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ text: fullText })
                });
                
                const data = await response.json();
                
                if (!data.success) {
                    showMessage(data.message || 'Ошибка оптимизации', 'error');
                    modalOptimizePreview.style.display = 'none';
                    return;
                }
                
                // Сохраняем результат
                optimizationResult = data;
                
                // Отображаем метрики
                const reduction = data.chars_before - data.chars_after;
                optimizeMetrics.innerHTML = `
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <div><strong>Символов до:</strong> ${data.chars_before.toLocaleString('ru-RU')}</div>
                        <div><strong>Символов после:</strong> ${data.chars_after.toLocaleString('ru-RU')}</div>
                        <div style="color: #2e7d32;"><strong>Экономия:</strong> ${reduction.toLocaleString('ru-RU')} (${data.reduction_pct.toFixed(1)}%)</div>
                    </div>
                `;
                
                // Отображаем текст с подсветкой
                renderHighlightedText(fullText, data.change_spans || []);
                
            } catch (error) {
                console.error('Ошибка оптимизации:', error);
                showMessage('Не удалось выполнить оптимизацию. Повторите позже', 'error');
                modalOptimizePreview.style.display = 'none';
            }
        });
    }
    
    // Отображение текста с подсветкой изменений
    function renderHighlightedText(originalText, changeSpans) {
        if (!changeSpans || changeSpans.length === 0) {
            optimizeTextPreview.textContent = originalText;
            return;
        }
        
        // Создаём массив для хранения частей текста
        const parts = [];
        let lastIndex = 0;
        
        // Сортируем spans по позиции начала
        const sortedSpans = [...changeSpans].sort((a, b) => a.start - b.start);
        
        // Объединяем пересекающиеся spans
        const mergedSpans = [];
        for (const span of sortedSpans) {
            if (mergedSpans.length === 0) {
                mergedSpans.push(span);
            } else {
                const lastSpan = mergedSpans[mergedSpans.length - 1];
                if (span.start <= lastSpan.end) {
                    // Объединяем
                    lastSpan.end = Math.max(lastSpan.end, span.end);
                    lastSpan.reason += `; ${span.reason}`;
                } else {
                    mergedSpans.push(span);
                }
            }
        }
        
        // Создаём HTML с подсветкой
        mergedSpans.forEach(span => {
            // Добавляем текст до span
            if (lastIndex < span.start) {
                const normalText = escapeHtml(originalText.slice(lastIndex, span.start));
                parts.push(normalText);
            }
            
            // Добавляем подсвеченный текст
            const highlightedText = escapeHtml(originalText.slice(span.start, span.end));
            parts.push(`<span style="background-color: #fff59d;" title="${escapeHtml(span.reason)}">${highlightedText}</span>`);
            
            lastIndex = span.end;
        });
        
        // Добавляем оставшийся текст
        if (lastIndex < originalText.length) {
            const remainingText = escapeHtml(originalText.slice(lastIndex));
            parts.push(remainingText);
        }
        
        optimizeTextPreview.innerHTML = parts.join('');
    }
    
    // Применение оптимизации
    if (btnApplyOptimization) {
        btnApplyOptimization.addEventListener('click', function() {
            if (!optimizationResult) {
                showMessage('Нет данных оптимизации', 'error');
                return;
            }
            
            // Применяем оптимизированный текст
            const optimizedText = optimizationResult.optimized_text;
            
            // Разделяем текст обратно на промпт и документы
            // (простая эвристика: первый абзац - промпт, остальное - документы)
            const lines = optimizedText.split('\n');
            const firstEmptyLine = lines.findIndex(line => line.trim() === '');
            
            if (firstEmptyLine > 0) {
                const promptPart = lines.slice(0, firstEmptyLine).join('\n');
                const docsPart = lines.slice(firstEmptyLine + 1).join('\n');
                
                if (ragPromptText) ragPromptText.value = promptPart;
                if (ragDocumentsText) ragDocumentsText.value = docsPart;
            } else {
                // Если нет разделения, весь текст в документы
                if (ragDocumentsText) ragDocumentsText.value = optimizedText;
            }
            
            // Показываем уведомление
            const reduction = optimizationResult.chars_before - optimizationResult.chars_after;
            showMessage(`Оптимизировано: −${reduction.toLocaleString('ru-RU')} символов (−${optimizationResult.reduction_pct.toFixed(1)}%)`, 'success');
            
            // Закрываем модалку
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
        });
    }
    
    // Отмена оптимизации
    if (btnCancelOptimization) {
        btnCancelOptimization.addEventListener('click', function() {
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
        });
    }
    
    // Закрытие по крестику
    if (optimizePreviewClose) {
        optimizePreviewClose.addEventListener('click', function() {
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
        });
    }
    
    // Закрытие по клику вне модалки
    if (modalOptimizePreview) {
        modalOptimizePreview.addEventListener('click', function(e) {
            if (e.target === modalOptimizePreview) {
                modalOptimizePreview.style.display = 'none';
                optimizationResult = null;
            }
        });
    }
    
    // Вспомогательная функция для экранирования HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Вспомогательная функция для показа сообщений
    function showMessage(message, type) {
        if (window.showMessage) {
            window.showMessage(message);
        } else if (window.alert) {
            alert(message);
        } else {
            console.log(message);
        }
    }
    
})();
