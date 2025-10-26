// AI Analysis Module
(function() {
    'use strict';

    // Элементы DOM
    const aiAnalysisBtn = document.getElementById('aiAnalysisBtn');
    const aiPromptModal = document.getElementById('aiPromptModal');
    const aiPromptClose = document.getElementById('aiPromptClose');
    const aiPromptText = document.getElementById('aiPromptText');
    const savePromptBtn = document.getElementById('savePromptBtn');
    const loadPromptBtn = document.getElementById('loadPromptBtn');
    const optimizeTextBtn = document.getElementById('optimizeTextBtn');
    const cancelAiAnalysisBtn = document.getElementById('cancelAiAnalysisBtn');
    const startAiAnalysisBtn = document.getElementById('startAiAnalysisBtn');
    const selectedFilesCount = document.getElementById('selectedFilesCount');
    const estimatedSize = document.getElementById('estimatedSize');
    
    const aiResultModal = document.getElementById('aiResultModal');
    const aiResultClose = document.getElementById('aiResultClose');
    const aiResultText = document.getElementById('aiResultText');
    const copyResultBtn = document.getElementById('copyResultBtn');
    const saveResultBtn = document.getElementById('saveResultBtn');
    const closeResultBtn = document.getElementById('closeResultBtn');
    
    const aiProgressModal = document.getElementById('aiProgressModal');
    const aiProgressStatus = document.getElementById('aiProgressStatus');
    
    const promptListModal = document.getElementById('promptListModal');
    const promptListClose = document.getElementById('promptListClose');
    const closePromptListBtn = document.getElementById('closePromptListBtn');
    const promptList = document.getElementById('promptList');

    let currentText = '';
    let maxRequestSize = 4096;

    // Элементы редактора оптимизации
    const aiOptimizeModal = document.getElementById('aiOptimizeModal');
    const aiOptimizeClose = document.getElementById('aiOptimizeClose');
    const optPromptText = document.getElementById('optPromptText');
    const optDocsContainer = document.getElementById('optDocsContainer');
    const optInfo = document.getElementById('optInfo');
    const optBackBtn = document.getElementById('optBackBtn');
    const optAutoBtn = document.getElementById('optAutoBtn');
    const optSaveBtn = document.getElementById('optSaveBtn');
    const optDeleteBtn = document.getElementById('optDeleteBtn');
    const optAnalyzeBtn = document.getElementById('optAnalyzeBtn');
    const optCancelBtn = document.getElementById('optCancelBtn');
    
    // Класс подсветки удаляемого фрагмента
    const DELETE_CLASS = 'to-delete';
    
    // CSS для подсветки (минимально)
    (function injectOptimizeStyles(){
        const style = document.createElement('style');
        style.textContent = `
            .opt-doc { margin:10px 0; padding:8px; border:1px solid #eee; border-radius:4px; }
            .opt-doc-title { font-weight:bold; margin-bottom:6px; }
            .opt-block { padding:2px 4px; border-radius:3px; cursor:pointer; }
            .opt-block.${DELETE_CLASS} { background-color: #ffe6ea; }
            .opt-sep { margin:8px 0; border-top:1px dashed #ccc; }
            .opt-header { background:#f7f7f7; padding:6px; border-radius:4px; }
        `;
        document.head.appendChild(style);
    })();

    // Открытие модального окна промпта
    if (aiAnalysisBtn) {
        aiAnalysisBtn.addEventListener('click', function() {
            const selectedFiles = getSelectedFiles();
            
            if (selectedFiles.length === 0) {
                showMessage('Пожалуйста, выберите файлы для анализа (установите галочки)', 'error');
                return;
            }
            
            // Загружаем последний промпт и затем обновляем информацию
            loadLastPrompt().then(() => {
                // Обновляем информацию после загрузки промпта
                updatePromptInfo(selectedFiles);
            });
            
            // Показываем модальное окно
            aiPromptModal.style.display = 'block';
        });
    }

    // Закрытие модальных окон
    if (aiPromptClose) {
        aiPromptClose.addEventListener('click', function() {
            aiPromptModal.style.display = 'none';
        });
    }

    if (cancelAiAnalysisBtn) {
        cancelAiAnalysisBtn.addEventListener('click', function() {
            aiPromptModal.style.display = 'none';
        });
    }

    if (aiResultClose) {
        aiResultClose.addEventListener('click', function() {
            aiResultModal.style.display = 'none';
        });
    }

    if (closeResultBtn) {
        closeResultBtn.addEventListener('click', function() {
            aiResultModal.style.display = 'none';
        });
    }

    if (promptListClose) {
        promptListClose.addEventListener('click', function() {
            promptListModal.style.display = 'none';
        });
    }

    if (closePromptListBtn) {
        closePromptListBtn.addEventListener('click', function() {
            promptListModal.style.display = 'none';
        });
    }

    // Закрытие модальных окон при клике вне их
    window.addEventListener('click', function(event) {
        if (event.target === aiPromptModal) {
            aiPromptModal.style.display = 'none';
        }
        if (event.target === aiResultModal) {
            aiResultModal.style.display = 'none';
        }
        if (event.target === promptListModal) {
            promptListModal.style.display = 'none';
        }
    });

    // Используем глобальную функцию getSelectedFiles из script.js
    function getSelectedFiles() {
        return window.getSelectedFiles ? window.getSelectedFiles() : [];
    }

    // Обновить информацию о выборе
    function updatePromptInfo(selectedFiles) {
        if (selectedFilesCount) {
            selectedFilesCount.textContent = `Файлов выбрано: ${selectedFiles.length}`;
        }
        
        // Получаем актуальные размеры с сервера
        updateSizeInfo(selectedFiles, aiPromptText.value);
    }
    
    // Обновить информацию о размерах
    function updateSizeInfo(selectedFiles, prompt) {
        if (!estimatedSize) return;
        
        estimatedSize.textContent = 'Подсчёт размера...';
        
        fetch('/ai_analysis/get_text_size', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_paths: selectedFiles,
                prompt: prompt
            })
        })
        .then(response => response.json())
    .then(data => {
            if (data.success) {
                const textSize = data.text_size || 0;
                const promptSize = data.prompt_size || 0;
                const totalSize = data.total_size || 0;
        const maxSize = data.max_size || 4096;
        // Обновляем глобальный лимит, если пришёл с сервера
        maxRequestSize = maxSize;
                const exceeds = data.exceeds_limit || false;
                const excess = data.excess || 0;
                
                let sizeText = `📄 Документ: ${textSize.toLocaleString()} симв. | 📝 Промпт: ${promptSize.toLocaleString()} симв.\n`;
                sizeText += `📊 Итого: ${totalSize.toLocaleString()} симв. | ✅ Лимит: ${maxSize.toLocaleString()} симв.`;
                
                if (exceeds) {
                    sizeText += `\n⚠️ ПРЕВЫШЕНИЕ: ${excess.toLocaleString()} симв. — требуется оптимизация!`;
                    estimatedSize.style.color = '#d32f2f';
                    estimatedSize.style.fontWeight = 'bold';
                } else {
                    const remaining = maxSize - totalSize;
                    sizeText += `\n✓ Запас: ${remaining.toLocaleString()} симв.`;
                    estimatedSize.style.color = '#2e7d32';
                    estimatedSize.style.fontWeight = 'normal';
                }
                
                estimatedSize.textContent = sizeText;
            } else {
                estimatedSize.textContent = `Ошибка подсчёта: ${data.message}`;
                estimatedSize.style.color = '#d32f2f';
            }
        })
        .catch(error => {
            estimatedSize.textContent = `Ошибка подсчёта размера: ${error}`;
            estimatedSize.style.color = '#d32f2f';
        });
    }

    // Загрузить последний использованный промпт
    function loadLastPrompt() {
        return fetch('/ai_analysis/prompts/last')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.prompt) {
                    aiPromptText.value = data.prompt;
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки промпта:', error);
            });
    }

    // Сохранить промпт
    if (savePromptBtn) {
        savePromptBtn.addEventListener('click', function() {
            const promptText = aiPromptText.value.trim();
            
            if (!promptText) {
                showMessage('Промпт пуст', 'error');
                return;
            }
            
            const filename = window.prompt('Введите имя файла для сохранения промпта (без расширения):');
            
            if (!filename) {
                return;
            }
            
            fetch('/ai_analysis/prompts/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    prompt: promptText,
                    filename: filename
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(data.message, 'success');
                } else {
                    showMessage(data.message, 'error');
                }
            })
            .catch(error => {
                showMessage('Ошибка сохранения промпта: ' + error, 'error');
            });
        });
    }

    // Загрузить промпт
    if (loadPromptBtn) {
        loadPromptBtn.addEventListener('click', function() {
            // Загружаем список промптов
            fetch('/ai_analysis/prompts/list')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.prompts && data.prompts.length > 0) {
                        showPromptList(data.prompts);
                    } else {
                        showMessage('Нет сохранённых промптов', 'info');
                    }
                })
                .catch(error => {
                    showMessage('Ошибка загрузки списка промптов: ' + error, 'error');
                });
        });
    }

    // Показать список промптов
    function showPromptList(prompts) {
        promptList.innerHTML = '';
        
        prompts.forEach(filename => {
            const item = document.createElement('div');
            item.style.cssText = 'padding: 10px; margin: 5px 0; background-color: #f5f5f5; border-radius: 4px; cursor: pointer; transition: background-color 0.2s;';
            item.textContent = filename;
            
            item.addEventListener('mouseenter', function() {
                this.style.backgroundColor = '#e0e0e0';
            });
            
            item.addEventListener('mouseleave', function() {
                this.style.backgroundColor = '#f5f5f5';
            });
            
            item.addEventListener('click', function() {
                loadPromptFile(filename);
                promptListModal.style.display = 'none';
            });
            
            promptList.appendChild(item);
        });
        
        promptListModal.style.display = 'block';
    }

    // Загрузить файл промпта
    function loadPromptFile(filename) {
        fetch(`/ai_analysis/prompts/load/${encodeURIComponent(filename)}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.prompt) {
                    aiPromptText.value = data.prompt;
                    showMessage('Промпт загружен', 'success');
                } else {
                    showMessage(data.message, 'error');
                }
            })
            .catch(error => {
                showMessage('Ошибка загрузки промпта: ' + error, 'error');
            });
    }

    // Оптимизировать текст
    if (optimizeTextBtn) {
        optimizeTextBtn.addEventListener('click', async function() {
            const selectedFiles = getSelectedFiles();
            // Открываем модал сразу, тексты подгружаем асинхронно
            openOptimizeModal(aiPromptText.value, []);
            optInfo.textContent = selectedFiles.length === 0 ? 'Файлы не выбраны. Отметьте галочками документы слева.' : 'Загрузка текстов выбранных документов...';

            if (selectedFiles.length === 0) {
                showMessage('Не выбраны файлы для оптимизации', 'error');
                return;
            }

            try {
                const res = await fetch('/ai_analysis/get_texts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_paths: selectedFiles })
                });
                const data = await res.json();
                if (!data.success) {
                    optInfo.textContent = data.message || 'Не удалось получить тексты';
                    showMessage(data.message || 'Не удалось получить тексты', 'error');
                    return;
                }
                renderDocsForOptimize(data.docs || []);
                updateOptimizeInfo();
            } catch (e) {
                optInfo.textContent = 'Ошибка загрузки текстов';
                showMessage('Ошибка загрузки текстов: ' + e, 'error');
            }
        });
    }

    // Снэпшот исходного состояния модала (для отмены)
    let optimizeSnapshot = null;

    function openOptimizeModal(promptValue, docs) {
        optPromptText.value = promptValue || '';
        renderDocsForOptimize(docs);
        updateOptimizeInfo();
        aiOptimizeModal.style.display = 'block';
        // Сохраняем исходный HTML, чтобы можно было легко откатить
        optimizeSnapshot = {
            prompt: optPromptText.value,
            docsHtml: optDocsContainer.innerHTML
        };
    }

    function renderDocsForOptimize(docs) {
        optDocsContainer.innerHTML = '';
        docs.forEach((doc, idx) => {
            const wrap = document.createElement('div');
            wrap.className = 'opt-doc';
            const title = document.createElement('div');
            title.className = 'opt-doc-title';
            title.textContent = `${idx+1}. ${doc.path}`;
            const body = document.createElement('div');
            // Разбиваем текст на абзацы/строки
            const lines = (doc.text || '').split(/\n+/);
            lines.forEach(line => {
                const span = document.createElement('span');
                span.className = 'opt-block';
                span.textContent = line;
                span.dataset.length = String(line.length);
                span.addEventListener('click', () => {
                    span.classList.toggle(DELETE_CLASS);
                    updateOptimizeInfo();
                });
                body.appendChild(span);
                body.appendChild(document.createElement('br'));
            });
            wrap.appendChild(title);
            wrap.appendChild(body);
            // Разделитель между документами
            const sep = document.createElement('div');
            sep.className = 'opt-sep';
            optDocsContainer.appendChild(wrap);
            optDocsContainer.appendChild(sep);
        });
    }

    function collectOptimizedPlainText() {
        // Собираем текст без подсвеченных блоков; без визуальных разделителей
        const parts = [];
        const docs = optDocsContainer.querySelectorAll('.opt-doc');
        docs.forEach(doc => {
            const blocks = doc.querySelectorAll('.opt-block');
            const rows = [];
            blocks.forEach(bl => {
                if (!bl.classList.contains(DELETE_CLASS)) {
                    rows.push(bl.textContent || '');
                }
            });
            parts.push(rows.join('\n'));
        });
        return parts.join('\n\n');
    }

    function updateOptimizeInfo() {
        const textOnly = collectOptimizedPlainText();
        const textSize = textOnly.length;
        const promptSize = (optPromptText.value || '').length;
        const total = textSize + promptSize + 2;
        const maxSize = maxRequestSize;
        const exceeds = total > maxSize;
        optInfo.textContent = `📄 Документ: ${textSize} симв. | 📝 Промпт: ${promptSize} симв. | 📊 Итого: ${total} / ${maxSize} симв.` + (exceeds ? `  ⚠️ Превышение на ${total - maxSize}` : `  ✓ ОК`);
        optInfo.style.color = exceeds ? '#d32f2f' : '#2e7d32';
    }

    // Авто-оптимизация: подсвечиваем длинные строки (>200 символов)
    if (optAutoBtn) {
        optAutoBtn.addEventListener('click', () => {
            optDocsContainer.querySelectorAll('.opt-block').forEach(bl => {
                const L = parseInt(bl.dataset.length || '0', 10);
                if (L > 200) bl.classList.add(DELETE_CLASS);
            });
            updateOptimizeInfo();
        });
    }

    // Удалить подсвеченное
    if (optDeleteBtn) {
        optDeleteBtn.addEventListener('click', () => {
            const count = optDocsContainer.querySelectorAll('.opt-block.'+DELETE_CLASS).length;
            if (count === 0) {
                showMessage('Нет подсвеченных фрагментов для удаления', 'info');
                return;
            }
            if (!confirm(`Будет удалено фрагментов: ${count}. Подтвердить?`)) return;
            optDocsContainer.querySelectorAll('.opt-block.'+DELETE_CLASS).forEach(bl => bl.remove());
            updateOptimizeInfo();
        });
    }

    // Сохранить рабочее состояние в файл
    if (optSaveBtn) {
        optSaveBtn.addEventListener('click', async () => {
            const docsPayload = [];
            const docs = optDocsContainer.querySelectorAll('.opt-doc');
            docs.forEach(doc => {
                const title = doc.querySelector('.opt-doc-title')?.textContent || '';
                const text = Array.from(doc.querySelectorAll('.opt-block'))
                    .map(bl => bl.textContent || '')
                    .join('\n');
                docsPayload.push({ path: title.replace(/^\d+\.\s*/, ''), text });
            });
            const res = await fetch('/ai_analysis/workspace/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: optPromptText.value, docs: docsPayload })
            });
            const data = await res.json();
            if (data.success) {
                showMessage('Воркспейс сохранён', 'success');
            } else {
                showMessage(data.message || 'Ошибка сохранения воркспейса', 'error');
            }
        });
    }

    // Назад — вернуться к окну Настройка анализа
    if (optBackBtn) {
        optBackBtn.addEventListener('click', () => {
            aiOptimizeModal.style.display = 'none';
            aiPromptModal.style.display = 'block';
        });
    }

    // Закрыть редактор
    if (aiOptimizeClose) {
        aiOptimizeClose.addEventListener('click', () => {
            aiOptimizeModal.style.display = 'none';
        });
    }

    // Отменить изменения — откат к снэпшоту
    if (optCancelBtn) {
        optCancelBtn.addEventListener('click', () => {
            if (optimizeSnapshot) {
                optPromptText.value = optimizeSnapshot.prompt;
                optDocsContainer.innerHTML = optimizeSnapshot.docsHtml;
                // Повесим обработчики повторно на восстановленные блоки
                optDocsContainer.querySelectorAll('.opt-block').forEach(span => {
                    span.addEventListener('click', () => {
                        span.classList.toggle(DELETE_CLASS);
                        updateOptimizeInfo();
                    });
                });
                updateOptimizeInfo();
            }
        });
    }

    // Пересчитывать размеры при изменении промпта в редакторе
    if (optPromptText) {
        let t;
        optPromptText.addEventListener('input', () => {
            clearTimeout(t);
            t = setTimeout(updateOptimizeInfo, 300);
        });
    }

    // Начать анализ с текущей версией текста
    if (optAnalyzeBtn) {
        optAnalyzeBtn.addEventListener('click', async () => {
            const selectedFiles = getSelectedFiles();
            const prompt = optPromptText.value.trim();
            const overrideText = collectOptimizedPlainText();
            if (!prompt) { showMessage('Промпт не может быть пустым', 'error'); return; }

            aiOptimizeModal.style.display = 'none';
            aiProgressModal.style.display = 'block';
            aiProgressStatus.textContent = 'Отправка запроса...';

            try {
                const resp = await fetch('/ai_analysis/analyze', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_paths: selectedFiles, prompt, max_request_size: maxRequestSize, override_text: overrideText })
                });
                const data = await resp.json();
                aiProgressModal.style.display = 'none';
                if (data.success) {
                    aiResultText.value = data.response;
                    aiResultModal.style.display = 'block';
                } else {
                    aiPromptModal.style.display = 'block';
                    showMessage(data.message || 'Ошибка анализа', 'error');
                }
            } catch (e) {
                aiProgressModal.style.display = 'none';
                aiPromptModal.style.display = 'block';
                showMessage('Ошибка AI анализа: ' + e, 'error');
            }
        });
    }

    // Обновить размеры при изменении промпта
    if (aiPromptText) {
        let updateTimeout;
        aiPromptText.addEventListener('input', function() {
            clearTimeout(updateTimeout);
            updateTimeout = setTimeout(() => {
                const selectedFiles = getSelectedFiles();
                if (selectedFiles.length > 0) {
                    updateSizeInfo(selectedFiles, this.value);
                }
            }, 500); // Обновляем с задержкой, чтобы не спамить запросы
        });
    }
    
    // Начать AI анализ
    if (startAiAnalysisBtn) {
        startAiAnalysisBtn.addEventListener('click', function() {
            const selectedFiles = getSelectedFiles();
            const prompt = aiPromptText.value.trim();
            
            if (selectedFiles.length === 0) {
                showMessage('Не выбраны файлы', 'error');
                return;
            }
            
            if (!prompt) {
                showMessage('Промпт не может быть пустым', 'error');
                return;
            }
            
            // Закрываем модальное окно промпта
            aiPromptModal.style.display = 'none';
            
            // Показываем прогресс
            aiProgressModal.style.display = 'block';
            aiProgressStatus.textContent = 'Отправка запроса...';
            
            // Отправляем запрос
            fetch('/ai_analysis/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_paths: selectedFiles,
                    prompt: prompt,
                    max_request_size: maxRequestSize
                })
            })
            .then(response => response.json())
            .then(data => {
                // Закрываем прогресс
                aiProgressModal.style.display = 'none';
                
                if (data.success) {
                    // Показываем результат
                    aiResultText.value = data.response;
                    aiResultModal.style.display = 'block';
                } else {
                    // Возвращаем пользователя в окно настроек
                    aiPromptModal.style.display = 'block';
                    
                    // Если превышен лимит, показываем информацию
                    if (data.current_size && data.max_size) {
                        const msg = `${data.message}\n\nТекущий размер: ${data.current_size} символов\nМаксимальный размер: ${data.max_size} символов\nПревышение: ${data.excess} символов\n\nИспользуйте кнопку "Оптимизировать текст" или отредактируйте промпт.`;
                        showMessage(msg, 'error');
                        
                        // Сохраняем текст для возможной оптимизации
                        if (data.text) {
                            currentText = data.text;
                        }
                        
                        // Обновляем информацию о размерах в окне
                        updateSizeInfo(selectedFiles, prompt);
                    } else {
                        showMessage(data.message, 'error');
                    }
                }
            })
            .catch(error => {
                aiProgressModal.style.display = 'none';
                aiPromptModal.style.display = 'block';
                showMessage('Ошибка AI анализа: ' + error, 'error');
            });
        });
    }

    // Копировать результат в буфер обмена
    if (copyResultBtn) {
        copyResultBtn.addEventListener('click', function() {
            const text = aiResultText.value;
            
            if (!text) {
                showMessage('Нет текста для копирования', 'error');
                return;
            }
            
            navigator.clipboard.writeText(text)
                .then(() => {
                    showMessage('Результат скопирован в буфер обмена', 'success');
                })
                .catch(error => {
                    showMessage('Ошибка копирования: ' + error, 'error');
                });
        });
    }

    // Сохранить результат в файл
    if (saveResultBtn) {
        saveResultBtn.addEventListener('click', function() {
            const text = aiResultText.value;
            
            if (!text) {
                showMessage('Нет текста для сохранения', 'error');
                return;
            }
            
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            const filename = `ai_analysis_${timestamp}.txt`;
            
            const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            showMessage(`Результат сохранён в файл: ${filename}`, 'success');
        });
    }

    // Используем глобальную функцию showMessage из script.js
    function showMessage(message, type) {
        if (window.showMessage) {
            window.showMessage(message);
        } else {
            alert(message);
        }
    }

})();
