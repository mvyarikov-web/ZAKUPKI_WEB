// Text Optimization Module
(function() {
    'use strict';

    // Вспомогательная функция для показа сообщений в модалке
    function showModalMessage(message, type) {
        console.log('[TextOptimizer]', type, message);
        const messageArea = document.getElementById('optimize-message-area');
        if (messageArea) {
            messageArea.textContent = message;
            messageArea.className = 'modal-message-area ' + (type || 'info');
            messageArea.style.display = 'block';
        }
    }
    
    // Функция для скрытия сообщения
    function hideModalMessage() {
        const messageArea = document.getElementById('optimize-message-area');
        if (messageArea) {
            messageArea.style.display = 'none';
        }
    }

    // Вспомогательная функция для экранирования HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

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
    
    console.log('[TextOptimizer] Инициализация модуля');
    console.log('[TextOptimizer] Кнопка найдена:', !!btnOptimizeText);
    console.log('[TextOptimizer] Модалка найдена:', !!modalOptimizePreview);
    console.log('[TextOptimizer] ragPromptText найден:', !!ragPromptText);
    console.log('[TextOptimizer] ragDocumentsText найден:', !!ragDocumentsText);
    
    // Состояние
    let optimizationResult = null;
    
    // Открытие модалки оптимизации
    if (btnOptimizeText) {
        console.log('[TextOptimizer] Добавлен обработчик на кнопку');
        btnOptimizeText.addEventListener('click', async function(e) {
            console.log('[TextOptimizer] Клик по кнопке оптимизации');
            e.preventDefault();
            e.stopPropagation();
            
            // Собираем текст для оптимизации
            const promptText = ragPromptText ? ragPromptText.value : '';
            const docsText = ragDocumentsText ? ragDocumentsText.value : '';
            const fullText = `${promptText}\n\n${docsText}`.trim();
            
            console.log('[TextOptimizer] Длина текста:', fullText.length);
            
            if (!fullText) {
                // Показываем модалку с сообщением об ошибке
                modalOptimizePreview.style.display = 'block';
                hideModalMessage();
                showModalMessage('Нет текста для оптимизации. Пожалуйста, добавьте текст в поля промпта или документов.', 'error');
                optimizeMetrics.innerHTML = '<div style="color: #999;">Нет данных</div>';
                optimizeTextPreview.textContent = '';
                return;
            }
            
            // Показываем модалку с загрузкой
            console.log('[TextOptimizer] Открываем модалку');
            modalOptimizePreview.style.display = 'block';
            hideModalMessage();
            optimizeMetrics.textContent = 'Анализ текста...';
            optimizeTextPreview.textContent = 'Подождите, выполняется оптимизация...';
            
            try {
                console.log('[TextOptimizer] Отправка запроса на сервер');
                // Отправляем запрос на оптимизацию
                const response = await fetch('/ai_analysis/optimize/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ text: fullText })
                });
                
                console.log('[TextOptimizer] Ответ получен, статус:', response.status);
                const data = await response.json();
                console.log('[TextOptimizer] Данные:', data);
                
                if (!data.success) {
                    console.warn('[TextOptimizer] Оптимизация неуспешна:', data.message);
                    showModalMessage(data.message || 'Ошибка оптимизации', 'error');
                    optimizeMetrics.innerHTML = '<div style="color: #999;">Нет данных</div>';
                    optimizeTextPreview.textContent = '';
                    return;
                }
                
                // Сохраняем результат
                optimizationResult = data;
                console.log('[TextOptimizer] Результат сохранён, change_spans:', data.change_spans?.length);
                
                // Если есть информационное сообщение (например, "текст уже оптимален")
                if (data.info_message) {
                    showModalMessage(data.info_message, 'info');
                } else {
                    hideModalMessage();
                }
                
                // Отображаем метрики
                const reduction = data.chars_before - data.chars_after;
                optimizeMetrics.innerHTML = `
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <div><strong>Символов до:</strong> ${data.chars_before.toLocaleString('ru-RU')}</div>
                        <div><strong>Символов после:</strong> ${data.chars_after.toLocaleString('ru-RU')}</div>
                        <div style="color: ${reduction > 0 ? '#2e7d32' : '#999'};"><strong>Экономия:</strong> ${reduction.toLocaleString('ru-RU')} (${data.reduction_pct.toFixed(1)}%)</div>
                    </div>
                `;
                
                console.log('[TextOptimizer] Метрики отображены, вызываем renderHighlightedText');
                // Отображаем текст с подсветкой (даже если изменений нет)
                renderHighlightedText(fullText, data.change_spans || []);
                console.log('[TextOptimizer] Модалка готова к показу');
                
            } catch (error) {
                console.error('[TextOptimizer] Ошибка оптимизации:', error);
                showModalMessage('Не удалось выполнить оптимизацию. Повторите позже', 'error');
                optimizeMetrics.innerHTML = '<div style="color: #999;">Ошибка</div>';
                optimizeTextPreview.textContent = '';
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
            const message = `Оптимизировано: −${reduction.toLocaleString('ru-RU')} символов (−${optimizationResult.reduction_pct.toFixed(1)}%)`;
            
            // Используем глобальную функцию showMessage если есть
            if (window.showMessage) {
                window.showMessage(message);
            } else {
                console.log('[TextOptimizer]', message);
            }
            
            // Закрываем модалку
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
            hideModalMessage();
        });
    }
    
    // Отмена оптимизации
    if (btnCancelOptimization) {
        btnCancelOptimization.addEventListener('click', function() {
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
            hideModalMessage();
        });
    }
    
    // Закрытие по крестику
    if (optimizePreviewClose) {
        optimizePreviewClose.addEventListener('click', function() {
            modalOptimizePreview.style.display = 'none';
            optimizationResult = null;
            hideModalMessage();
        });
    }
    
    // Закрытие по клику вне модалки
    if (modalOptimizePreview) {
        modalOptimizePreview.addEventListener('click', function(e) {
            if (e.target === modalOptimizePreview) {
                modalOptimizePreview.style.display = 'none';
                optimizationResult = null;
                hideModalMessage();
            }
        });
    }
    
    console.log('[TextOptimizer] Модуль загружен и готов к работе');
    
})();
