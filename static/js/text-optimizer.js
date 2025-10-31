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
    const btnSaveOptimization = document.getElementById('btn-save-optimization');
    const optimizeMetrics = document.getElementById('optimize-metrics');
    const optimizeTextPreview = document.getElementById('optimize-text-preview');
    const btnPrevHighlight = document.getElementById('btn-prev-highlight');
    const btnNextHighlight = document.getElementById('btn-next-highlight');
    const highlightCounter = document.getElementById('highlight-counter');
    
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
    let currentHighlightIndex = -1;
    let highlightElements = [];
    let userModifiedSpans = new Set(); // Хранит ID span'ов, которые пользователь добавил/удалил
    
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
        highlightElements = [];
        currentHighlightIndex = -1;
        userModifiedSpans.clear();
        
        if (!changeSpans || changeSpans.length === 0) {
            optimizeTextPreview.textContent = originalText;
            updateHighlightCounter();
            setupClickHandlers();
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
                mergedSpans.push({...span, id: 0});
            } else {
                const lastSpan = mergedSpans[mergedSpans.length - 1];
                if (span.start <= lastSpan.end) {
                    // Объединяем
                    lastSpan.end = Math.max(lastSpan.end, span.end);
                    lastSpan.reason += `; ${span.reason}`;
                } else {
                    mergedSpans.push({...span, id: mergedSpans.length});
                }
            }
        }
        
        // Создаём HTML с подсветкой
        mergedSpans.forEach((span, index) => {
            // Добавляем текст до span
            if (lastIndex < span.start) {
                const normalText = escapeHtml(originalText.slice(lastIndex, span.start));
                parts.push(normalText);
            }
            
            // Добавляем подсвеченный текст (исходные подсветки оптимизатора)
            const highlightedText = escapeHtml(originalText.slice(span.start, span.end));
            parts.push(`<span class="highlight-span" data-span-id="${span.id}" style="background-color: #fff59d;" title="${escapeHtml(span.reason)}">${highlightedText}</span>`);
            
            lastIndex = span.end;
        });
        
        // Добавляем оставшийся текст
        if (lastIndex < originalText.length) {
            const remainingText = escapeHtml(originalText.slice(lastIndex));
            parts.push(remainingText);
        }
        
        optimizeTextPreview.innerHTML = parts.join('');
        
        // Собираем все элементы с подсветкой (исходные + пользовательские)
        highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span'));
        updateHighlightCounter();
        
        // Добавляем обработчики для выделения текста мышкой
        setupClickHandlers();
    }
    
    // Обновление счётчика подсветок
    function updateHighlightCounter() {
        const total = highlightElements.length;
        const current = currentHighlightIndex >= 0 ? currentHighlightIndex + 1 : 0;
        if (highlightCounter) {
            highlightCounter.textContent = `${current} / ${total}`;
        }
    }
    
    // Навигация к следующей подсветке
    function navigateToHighlight(direction) {
        // Обновляем список всех подсветок (исходные + пользовательские)
        highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span, .user-highlight'));
        
        if (highlightElements.length === 0) return;
        
        // Убираем границу у текущей подсветки
        if (currentHighlightIndex >= 0 && currentHighlightIndex < highlightElements.length) {
            highlightElements[currentHighlightIndex].style.outline = 'none';
        }
        
        // Вычисляем новый индекс
        if (direction === 'next') {
            currentHighlightIndex = (currentHighlightIndex + 1) % highlightElements.length;
        } else if (direction === 'prev') {
            currentHighlightIndex = currentHighlightIndex <= 0 
                ? highlightElements.length - 1 
                : currentHighlightIndex - 1;
        }
        
        // Подсвечиваем текущую подсветку
        const currentElement = highlightElements[currentHighlightIndex];
        currentElement.style.outline = '2px solid #ff9800';
        
        // Прокручиваем к элементу
        currentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        updateHighlightCounter();
    }
    
    // Построение финального текста с учётом пользовательских изменений
    function buildOptimizedTextFromDOM() {
        // Рекурсивная функция для обхода DOM и сбора текста
        function collectText(node, skipHighlights) {
            let text = '';
            
            node.childNodes.forEach(child => {
                if (child.nodeType === Node.TEXT_NODE) {
                    // Текстовый узел - добавляем его содержимое
                    text += child.textContent;
                } else if (child.nodeType === Node.ELEMENT_NODE) {
                    // Элемент
                    if (child.classList.contains('highlight-span')) {
                        // Исходная подсветка - пропускаем (будет удалена)
                        return;
                    } else if (child.classList.contains('user-highlight')) {
                        // Пользовательская подсветка - пропускаем (будет удалена)
                        return;
                    } else {
                        // Обычный элемент - рекурсивно собираем текст
                        text += collectText(child, skipHighlights);
                    }
                }
            });
            
            return text;
        }
        
        return collectText(optimizeTextPreview, true);
    }
    
    // Обработчики для выделения произвольного текста мышкой
    function setupClickHandlers() {
        // Обработчик выделения текста мышкой
        optimizeTextPreview.addEventListener('mouseup', function(e) {
            const selection = window.getSelection();
            const selectedText = selection.toString();
            
            // Если текст выделен
            if (selectedText.length > 0) {
                e.preventDefault();
                toggleSelectionHighlight(selection);
            }
        });
        
        // Клик по подсветке - снять подсветку с этого конкретного фрагмента
        optimizeTextPreview.addEventListener('click', function(e) {
            const target = e.target;
            
            // Клик по пользовательской подсветке - убрать её
            if (target.classList && target.classList.contains('user-highlight')) {
                e.stopPropagation();
                const highlightId = target.getAttribute('data-highlight-id');
                
                // Заменяем подсвеченный span обычным текстом
                const textNode = document.createTextNode(target.textContent);
                target.parentNode.replaceChild(textNode, target);
                
                userModifiedSpans.delete(highlightId);
                
                // Обновляем счётчик
                highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span, .user-highlight'));
                updateHighlightCounter();
            }
            
            // Клик по исходной подсветке оптимизатора - также убрать её
            if (target.classList && target.classList.contains('highlight-span')) {
                e.stopPropagation();
                
                // Заменяем подсвеченный span обычным текстом
                const textNode = document.createTextNode(target.textContent);
                target.parentNode.replaceChild(textNode, target);
                
                // Обновляем счётчик
                highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span, .user-highlight'));
                updateHighlightCounter();
            }
        });
    }
    
    // Переключение подсветки для выделенного текста
    function toggleSelectionHighlight(selection) {
        if (!selection.rangeCount) return;
        
        const range = selection.getRangeAt(0);
        
        // Проверяем, что выделение внутри optimizeTextPreview
        if (!optimizeTextPreview.contains(range.commonAncestorContainer)) {
            return;
        }
        
        // Проверяем, содержит ли выделение подсвеченный текст
        // Или находится ли выделение ВНУТРИ подсветки
        const tempDiv = document.createElement('div');
        tempDiv.appendChild(range.cloneContents());
        let hasHighlight = tempDiv.querySelector('.user-highlight, .highlight-span') !== null;
        
        // Также проверяем, находится ли начало или конец выделения внутри подсветки
        if (!hasHighlight) {
            const startContainer = range.startContainer;
            const endContainer = range.endContainer;
            
            // Проверяем родителей startContainer
            let node = startContainer.nodeType === Node.TEXT_NODE ? startContainer.parentNode : startContainer;
            while (node && node !== optimizeTextPreview) {
                if (node.classList && (node.classList.contains('highlight-span') || node.classList.contains('user-highlight'))) {
                    hasHighlight = true;
                    break;
                }
                node = node.parentNode;
            }
            
            // Проверяем родителей endContainer
            if (!hasHighlight) {
                node = endContainer.nodeType === Node.TEXT_NODE ? endContainer.parentNode : endContainer;
                while (node && node !== optimizeTextPreview) {
                    if (node.classList && (node.classList.contains('highlight-span') || node.classList.contains('user-highlight'))) {
                        hasHighlight = true;
                        break;
                    }
                    node = node.parentNode;
                }
            }
        }
        
        if (hasHighlight) {
            // Если в выделении есть подсветка - убираем её
            removeHighlightFromRange(range);
        } else {
            // Иначе добавляем подсветку
            addHighlightToRange(range);
        }
        
        // Снимаем выделение
        selection.removeAllRanges();
        
        // Обновляем счётчик
        highlightElements = Array.from(optimizeTextPreview.querySelectorAll('.highlight-span, .user-highlight'));
        updateHighlightCounter();
    }
    
    // Добавление подсветки к выделенному диапазону
    function addHighlightToRange(range) {
        try {
            const span = document.createElement('span');
            span.className = 'user-highlight';
            span.style.backgroundColor = '#fff59d';
            span.style.cursor = 'pointer';
            const highlightId = 'hl-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            span.setAttribute('data-highlight-id', highlightId);
            span.setAttribute('title', 'Кликните для снятия подсветки');
            
            range.surroundContents(span);
            userModifiedSpans.add(highlightId);
        } catch (err) {
            console.warn('[TextOptimizer] Не удалось обернуть выделение:', err);
            // Fallback: пробуем извлечь содержимое и обернуть
            try {
                const contents = range.extractContents();
                const span = document.createElement('span');
                span.className = 'user-highlight';
                span.style.backgroundColor = '#fff59d';
                span.style.cursor = 'pointer';
                const highlightId = 'hl-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
                span.setAttribute('data-highlight-id', highlightId);
                span.setAttribute('title', 'Кликните для снятия подсветки');
                span.appendChild(contents);
                range.insertNode(span);
                userModifiedSpans.add(highlightId);
            } catch (err2) {
                console.error('[TextOptimizer] Ошибка добавления подсветки:', err2);
            }
        }
    }
    
    // Удаление подсветки из диапазона
    function removeHighlightFromRange(range) {
        // Удаляем пользовательские подсветки
        const userHighlights = optimizeTextPreview.querySelectorAll('.user-highlight');
        userHighlights.forEach(hl => {
            const hlText = hl.textContent;
            const hlId = hl.getAttribute('data-highlight-id');
            
            // Проверяем, пересекается ли с выделением
            if (range.intersectsNode(hl)) {
                const textNode = document.createTextNode(hlText);
                hl.parentNode.replaceChild(textNode, hl);
                userModifiedSpans.delete(hlId);
            }
        });
        
        // Удаляем исходные подсветки оптимизатора
        const originalHighlights = optimizeTextPreview.querySelectorAll('.highlight-span');
        originalHighlights.forEach(hl => {
            const hlText = hl.textContent;
            
            // Проверяем, пересекается ли с выделением
            if (range.intersectsNode(hl)) {
                const textNode = document.createTextNode(hlText);
                hl.parentNode.replaceChild(textNode, hl);
            }
        });
    }
    
    // Навигация по подсветкам
    if (btnNextHighlight) {
        btnNextHighlight.addEventListener('click', function() {
            navigateToHighlight('next');
        });
    }
    
    if (btnPrevHighlight) {
        btnPrevHighlight.addEventListener('click', function() {
            navigateToHighlight('prev');
        });
    }
    
    // Горячие клавиши для навигации (Shift+Стрелки)
    document.addEventListener('keydown', function(e) {
        if (!modalOptimizePreview || modalOptimizePreview.style.display === 'none') {
            return; // Модалка не открыта
        }
        
        if (e.shiftKey && e.key === 'ArrowDown') {
            e.preventDefault();
            navigateToHighlight('next');
        } else if (e.shiftKey && e.key === 'ArrowUp') {
            e.preventDefault();
            navigateToHighlight('prev');
        }
    });
    
    // Применение правил оптимизации (повторная оптимизация текущего текста)
    if (btnApplyOptimization) {
        btnApplyOptimization.addEventListener('click', async function() {
            // Получаем текущий текст из превью (с учётом пользовательских изменений)
            const currentText = buildOptimizedTextFromDOM();
            
            if (!currentText || !currentText.trim()) {
                showModalMessage('Нет текста для оптимизации', 'error');
                return;
            }
            
            // Показываем индикатор загрузки
            hideModalMessage();
            optimizeMetrics.textContent = 'Повторный анализ текста...';
            optimizeTextPreview.textContent = 'Подождите, выполняется оптимизация...';
            
            try {
                // Отправляем запрос на оптимизацию
                const response = await fetch('/ai_analysis/optimize/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ text: currentText })
                });
                
                const data = await response.json();
                
                if (!data.success) {
                    showModalMessage(data.message || 'Ошибка оптимизации', 'error');
                    optimizeMetrics.innerHTML = '<div style="color: #999;">Нет данных</div>';
                    optimizeTextPreview.textContent = '';
                    return;
                }
                
                // Сохраняем результат
                optimizationResult = data;
                
                // Если есть информационное сообщение
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
                
                // Отображаем текст с подсветкой
                renderHighlightedText(currentText, data.change_spans || []);
                
            } catch (error) {
                console.error('[TextOptimizer] Ошибка повторной оптимизации:', error);
                showModalMessage('Не удалось выполнить оптимизацию. Повторите позже', 'error');
                optimizeMetrics.innerHTML = '<div style="color: #999;">Ошибка</div>';
                optimizeTextPreview.textContent = '';
            }
        });
    }
    
    // Сохранение оптимизации (применение к полям и закрытие окна)
    if (btnSaveOptimization) {
        btnSaveOptimization.addEventListener('click', function() {
            if (!optimizationResult) {
                showModalMessage('Нет данных оптимизации', 'error');
                return;
            }
            
            // Собираем финальный текст из DOM (с учётом всех пользовательских изменений)
            const optimizedText = buildOptimizedTextFromDOM();
            
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
            
            // Показываем success сообщение в RAG модалке
            if (window.MessageManager) {
                MessageManager.success(message, 'ragModal');
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
