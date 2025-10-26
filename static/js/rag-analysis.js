// RAG Analysis Module (под текущую разметку index.html)
(function() {
    'use strict';

    // Кнопки внизу модала AI-настроек
    const ragAnalysisBtn = document.getElementById('ragAnalysisBtn');
        const aiAnalysisBtn = document.getElementById('aiAnalysisBtn');

    // RAG-модал и элементы внутри
    const ragModal = document.getElementById('ragModal');
    const ragModalClose = document.getElementById('ragModalClose');
    const ragPromptText = document.getElementById('ragPromptText');
    const ragDocumentsText = document.getElementById('ragDocumentsText');
    const ragModelBtn = document.getElementById('ragModelBtn');
    const ragCurrentModel = document.getElementById('ragCurrentModel');
    const ragInfo = document.getElementById('ragInfo');
    const ragMetrics = document.getElementById('ragMetrics');
    const ragStartBtn = document.getElementById('ragStartBtn');
    const ragDeepMode = document.getElementById('ragDeepMode');
    const ragCancelBtn = document.getElementById('ragCancelBtn');
        const ragSavePromptBtn = document.getElementById('ragSavePromptBtn');
        const ragLoadPromptBtn = document.getElementById('ragLoadPromptBtn');

    // Модал выбора модели/цен
    const modelSelectModal = document.getElementById('modelSelectModal');
    const modelSelectClose = document.getElementById('modelSelectClose');
    const modelsList = document.getElementById('modelsList');
    const modelSaveBtn = document.getElementById('modelSaveBtn');
    const modelCancelBtn = document.getElementById('modelCancelBtn');
    const usdRubRateInput = document.getElementById('usdRubRate');

    // Результаты (переиспользуем общий AI-результат)
    const aiResultModal = document.getElementById('aiResultModal');
    const aiResultText = document.getElementById('aiResultText');
    const aiResultClose = document.getElementById('aiResultClose');

    // Модал выбора промпта (переиспользуем существующий)
    const promptListModal = document.getElementById('promptListModal');
    const promptList = document.getElementById('promptList');
    const promptListClose = document.getElementById('promptListClose');
    const closePromptListBtn = document.getElementById('closePromptListBtn');

    // Состояние
    let models = [];
    let selectedModelId = null;
    let debounceTimer = null;

    function getSelectedFiles() {
        return window.getSelectedFiles ? window.getSelectedFiles() : [];
    }

    function showMessage(message) {
        if (window.showMessage) return window.showMessage(message);
        alert(message);
    }
    
    // Функции для работы с курсом USD/RUB
    function getUsdRubRate() {
        if (!usdRubRateInput) return 0;
        const val = parseFloat(usdRubRateInput.value);
        return (val && val > 0) ? val : 0;
    }
    
    function loadUsdRubRate() {
        try {
            const saved = localStorage.getItem('usd_rub_rate');
            if (saved && usdRubRateInput) {
                usdRubRateInput.value = saved;
            }
        } catch (_) {}
    }
    
    function saveUsdRubRate() {
        try {
            const rate = getUsdRubRate();
            if (rate > 0) {
                localStorage.setItem('usd_rub_rate', rate.toString());
            } else {
                localStorage.removeItem('usd_rub_rate');
            }
        } catch (_) {}
    }

    // Загрузка/отрисовка моделей
    async function loadModels() {
        try {
            const res = await fetch('/ai_rag/models');
            if (!res.ok) {
                console.error('Ошибка загрузки моделей: HTTP', res.status);
                throw new Error(`HTTP ${res.status}`);
            }
            const data = await res.json();
            console.log('Загружены модели:', data);
            if (data.success) {
                models = data.models || [];
                selectedModelId = data.default_model || (models[0] && models[0].model_id) || null;
                console.log('Установлено моделей:', models.length, 'Выбрана:', selectedModelId);
                updateCurrentModelLabel();
            } else {
                console.error('Ошибка в данных моделей:', data);
            }
        } catch (e) {
            console.error('Ошибка загрузки моделей:', e);
        }
    }

    function updateCurrentModelLabel() {
        const m = models.find(x => x.model_id === selectedModelId);
        ragCurrentModel.textContent = `Модель: ${m ? m.display_name : 'не выбрана'}`;
    }

    function renderModelsList() {
        if (!modelsList) return;
        if (!models || models.length === 0) {
            modelsList.innerHTML = '<p>Модели не загружены</p>';
            return;
        }

        let html = '';
        models.forEach(m => {
            const checked = m.model_id === selectedModelId ? 'checked' : '';
                            const status = (m.enabled === false) ? '<span style="color:#d32f2f; font-size:12px;">не активна</span>' : '<span style="color:#2e7d32; font-size:12px;">активна</span>';
                            html += `
                                <div style="border:1px solid #ddd; border-radius:6px; padding:10px; margin-bottom:10px;">
                                    <div style="display:flex; gap:10px; align-items:center;">
                                        <input type="radio" name="rag-model" value="${m.model_id}" ${checked} />
                                        <div style="flex:1;">
                                            <div><strong>${m.display_name}</strong> <span style="color:#777; font-size:12px;">(${m.model_id})</span> · ${status}</div>
                                            <div style="color:#666; font-size:12px;">Контекст: ${Number(m.context_window_tokens || 0).toLocaleString()} токенов</div>
                                        </div>
                                        <div style="display:flex; gap:8px;">
                                            <label style="font-size:12px; color:#555;">Вход (за 1М): <input type="number" step="0.0001" min="0" data-price-in="${m.model_id}" value="${m.price_input_per_1m || 0}" style="width:120px;" /></label>
                                            <label style="font-size:12px; color:#555;">Выход (за 1М): <input type="number" step="0.0001" min="0" data-price-out="${m.model_id}" value="${m.price_output_per_1m || 0}" style="width:120px;" /></label>
                                        </div>
                                    </div>
                                </div>`;
        });
        modelsList.innerHTML = html;

        // Обработчики выбора модели
        modelsList.querySelectorAll('input[name="rag-model"]').forEach(r => {
            r.addEventListener('change', (e) => {
                selectedModelId = e.target.value;
                updateCurrentModelLabel();
                updateRagMetrics();
            });
        });
        
        // Обработчики изменения цен - обновляем локально модели и метрики
        modelsList.querySelectorAll('input[data-price-in], input[data-price-out]').forEach(inp => {
            inp.addEventListener('input', (e) => {
                const modelId = e.target.getAttribute('data-price-in') || e.target.getAttribute('data-price-out');
                const model = models.find(m => m.model_id === modelId);
                if (model) {
                    if (e.target.hasAttribute('data-price-in')) {
                        model.price_input_per_1m = parseFloat(e.target.value) || 0;
                    } else {
                        model.price_output_per_1m = parseFloat(e.target.value) || 0;
                    }
                    // Немедленно обновляем метрики
                    updateRagMetrics();
                }
            });
        });
        
        // Обработчик изменения курса
        if (usdRubRateInput) {
            usdRubRateInput.addEventListener('input', () => {
                updateRagMetrics();
            });
        }
    }

    async function saveModelPrices() {
        // Собираем значения из инпутов
        const inputsIn = modelsList.querySelectorAll('input[data-price-in]');
        const inputsOut = modelsList.querySelectorAll('input[data-price-out]');
        const toSave = [];

        inputsIn.forEach(inp => {
            const id = inp.getAttribute('data-price-in');
            const valIn = parseFloat(inp.value) || 0;
            const outInp = modelsList.querySelector(`input[data-price-out="${id}"]`);
            const valOut = outInp ? (parseFloat(outInp.value) || 0) : 0;
            toSave.push({ model_id: id, price_input_per_1m: valIn, price_output_per_1m: valOut });
        });

        // Отправляем по одному (минимальная правка бэка)
        for (const item of toSave) {
            await fetch('/ai_rag/models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(item)
            });
        }
        
        // Сохраняем выбранную модель как модель по умолчанию
        if (selectedModelId) {
            await fetch('/ai_rag/models/default', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: selectedModelId })
            });
        }
        
        // Сохраняем курс USD/RUB
        saveUsdRubRate();

        showMessage('Настройки сохранены');
        await loadModels();
        renderModelsList();
        updateRagMetrics();
    }

    // Загрузка текстов документов для редактирования
    async function fillDocumentsText() {
        const files = getSelectedFiles();
        if (!files || files.length === 0) return;
        try {
            const res = await fetch('/ai_analysis/get_texts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_paths: files })
            });
            const data = await res.json();
            if (data.success && Array.isArray(data.docs)) {
                const parts = data.docs.map(d => {
                    const p = d && d.path ? d.path : '(без имени)';
                    const t = d && typeof d.text === 'string' ? d.text : '';
                    return `===== ${p} =====\n${t}`;
                });
                ragDocumentsText.value = parts.join('\n\n---\n\n');
            } else {
                ragDocumentsText.value = '';
            }
        } catch (e) {
            console.error('Ошибка получения текстов:', e);
            ragDocumentsText.value = '';
        }
    }

    // Подсчёт метрик на лету (локально): ~4 символа = 1 токен
    function estimateTokens(chars) {
        return Math.max(0, Math.floor(chars / 4));
    }

    function getSelectedModelPrices() {
        const m = models.find(x => x.model_id === selectedModelId);
        return {
            inPrice: m ? (m.price_input_per_1m || 0) : 0,
            outPrice: m ? (m.price_output_per_1m || 0) : 0,
            name: m ? m.display_name : '—'
        };
    }

    function updateRagMetrics() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const prompt = (ragPromptText.value || '').trim();
            const docs = (ragDocumentsText.value || '').trim();

            const promptChars = prompt.length;
            const docsChars = docs.length;
            const totalChars = promptChars + docsChars;
            const inputTokens = estimateTokens(totalChars);
            const deep = !!(ragDeepMode && ragDeepMode.checked);
            const expectedOutput = deep ? 1200 : 600; // увеличиваем оценку вывода в глубокий режим
            const totalTokens = inputTokens + expectedOutput;

            const { inPrice, outPrice, name } = getSelectedModelPrices();
            let info = `Модель: ${name}. Символы: промпт ${promptChars.toLocaleString()}, документы ${docsChars.toLocaleString()}, всего ${totalChars.toLocaleString()}. Токены (оценка): вход ${inputTokens.toLocaleString()}, выход ${expectedOutput.toLocaleString()}, всего ${totalTokens.toLocaleString()}.`;

            if (inPrice > 0 || outPrice > 0) {
                const costIn = (inputTokens / 1_000_000) * inPrice;
                const costOut = (expectedOutput / 1_000_000) * outPrice;
                const totalCost = costIn + costOut;
                info += ` Стоимость (оценка): вход $${costIn.toFixed(4)}, выход $${costOut.toFixed(4)}, всего $${totalCost.toFixed(4)}`;
                
                // Добавляем пересчёт в рубли, если курс задан
                const rate = getUsdRubRate();
                if (rate > 0) {
                    const rubIn = costIn * rate;
                    const rubOut = costOut * rate;
                    const rubTotal = totalCost * rate;
                    info += ` (${rubIn.toFixed(2)}₽ / ${rubOut.toFixed(2)}₽ / ${rubTotal.toFixed(2)}₽)`;
                }
                info += '.';
            } else {
                info += ' Стоимость не рассчитана: укажите цены в таблице моделей.';
            }

            ragMetrics.textContent = info;
        }, 250);
    }

    // Анализ (через бэкенд /ai_rag/analyze)
    async function startAnalysis() {
        const files = getSelectedFiles();
        const prompt = (ragPromptText.value || '').trim();
        if (!prompt) {
            return showMessage('Введите промпт');
        }
        if (!files || files.length === 0) {
            return showMessage('Выберите файлы для анализа');
        }

        ragModal.style.display = 'none';
        showMessage('Выполняется AI анализ...');
        try {
            const res = await fetch('/ai_rag/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_paths: files,
                    prompt,
                    model_id: selectedModelId,
                    top_k: (ragDeepMode && ragDeepMode.checked) ? 8 : 5,
                    max_output_tokens: (ragDeepMode && ragDeepMode.checked) ? 1200 : 600,
                    temperature: 0.3
                })
            });
            const data = await res.json();
            if (data.success) {
                // Преобразуем result в текст для просмотра
                const text = typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2);
                aiResultText.value = text;
                aiResultModal.style.display = 'block';
                showMessage('Анализ выполнен успешно');
            } else {
                showMessage(data.message || 'Ошибка анализа');
            }
        } catch (e) {
            showMessage('Ошибка сети: ' + e.message);
        }
    }

    // Привязка событий
    async function openRag() {
        const files = getSelectedFiles();
        if (!files || files.length === 0) {
            return showMessage('Выберите файлы для анализа (галочки слева от файлов)');
        }
        await loadModels();
        await fillDocumentsText();
        
        // Загружаем последний промпт из localStorage, если он есть
        try {
            const lastPrompt = localStorage.getItem('last_loaded_prompt');
            if (lastPrompt && !ragPromptText.value.trim()) {
                ragPromptText.value = lastPrompt;
            }
        } catch (_) {}
        
        updateRagMetrics();
        try { autoResize(ragPromptText, 4); autoResize(ragDocumentsText, 10); } catch (_) {}
        ragModal.style.display = 'block';
    }
    if (ragAnalysisBtn) ragAnalysisBtn.addEventListener('click', openRag);
    if (aiAnalysisBtn) aiAnalysisBtn.addEventListener('click', openRag);

    if (ragModalClose) {
        ragModalClose.addEventListener('click', () => ragModal.style.display = 'none');
    }
    if (ragCancelBtn) {
        ragCancelBtn.addEventListener('click', () => ragModal.style.display = 'none');
    }
    if (ragModelBtn) {
        ragModelBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/ai_rag/status');
                const st = await res.json();
                if (st && st.success) {
                    showMessage(st.api_key_configured ? 'API-ключ настроен' : 'API-ключ не найден');
                }
            } catch (_) {}
            await loadModels();
            loadUsdRubRate(); // Загружаем курс из localStorage
            renderModelsList();
            modelSelectModal.style.display = 'block';
        });
    }
        if (ragAnalysisBtn) ragAnalysisBtn.addEventListener('click', openRag);
        if (aiAnalysisBtn) aiAnalysisBtn.addEventListener('click', openRag);
    if (modelSelectClose) {
        modelSelectClose.addEventListener('click', () => modelSelectModal.style.display = 'none');
    }
    if (modelCancelBtn) {
        modelCancelBtn.addEventListener('click', () => modelSelectModal.style.display = 'none');
    }
    if (modelSaveBtn) {
        modelSaveBtn.addEventListener('click', async () => {
            await saveModelPrices();
            modelSelectModal.style.display = 'none';
        });
    }
    // Кнопка «Обновить модели»
    const modelRefreshBtn = document.getElementById('modelRefreshBtn');
    if (modelRefreshBtn) {
        modelRefreshBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/ai_rag/models/refresh', { method: 'POST' });
                if (!res.ok) {
                    const txt = await res.text();
                    return showMessage('Не удалось обновить модели: ' + (txt || res.statusText));
                }
                const data = await res.json().catch(async () => ({ success: false, message: await res.text() }));
                if (data && data.success) {
                    showMessage(`Модели обновлены: добавлено ${data.added || 0}, обновлено ${data.updated || 0}.`);
                    await loadModels();
                    renderModelsList();
                    updateRagMetrics();
                } else {
                    showMessage((data && data.message) || 'Не удалось обновить список моделей');
                }
            } catch (e) {
                showMessage('Ошибка сети при обновлении моделей: ' + e.message);
            }
        });
    }
    if (ragStartBtn) {
        ragStartBtn.addEventListener('click', startAnalysis);
    }
    if (aiResultClose) {
        aiResultClose.addEventListener('click', () => aiResultModal.style.display = 'none');
    }

    // Живые метрики
    if (ragPromptText) ragPromptText.addEventListener('input', updateRagMetrics);
    if (ragDocumentsText) ragDocumentsText.addEventListener('input', updateRagMetrics);
        // Живые метрики + авто-ресайз
        function autoResize(el, minRows) {
            if (!el) return;
            el.style.height = 'auto';
            const lh = 18; // px
            const rows = Math.max(minRows, Math.ceil(el.scrollHeight / lh));
            el.style.height = (rows * lh) + 'px';
        }
        if (ragPromptText) ragPromptText.addEventListener('input', () => { updateRagMetrics(); autoResize(ragPromptText, 4); });
        if (ragDocumentsText) ragDocumentsText.addEventListener('input', () => { updateRagMetrics(); autoResize(ragDocumentsText, 10); });

        // Сохранить/Загрузить промпт в RAG
        if (ragSavePromptBtn) {
            ragSavePromptBtn.addEventListener('click', async () => {
                const prompt = (ragPromptText.value || '').trim();
                if (!prompt) return showMessage('Промпт пуст');
                const filename = window.prompt('Введите имя файла (без расширения):');
                if (!filename) return;
                try {
                    const res = await fetch('/ai_analysis/prompts/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ prompt, filename }) });
                    const data = await res.json();
                    showMessage(data.message || (data.success ? 'Промпт сохранён' : 'Не удалось сохранить промпт'));
                } catch (e) { showMessage('Ошибка сохранения: ' + e.message); }
            });
        }
        if (ragLoadPromptBtn) {
            ragLoadPromptBtn.addEventListener('click', async () => {
                try {
                    const res = await fetch('/ai_analysis/prompts/list');
                    const data = await res.json();
                    if (!data.success || !Array.isArray(data.prompts) || data.prompts.length === 0) {
                        return showMessage('Нет сохранённых промптов');
                    }
                    // Очистить и наполнить список кликабельными пунктами с превью
                    if (!promptList || !promptListModal) return;
                    promptList.innerHTML = '';
                    // Для каждого файла запросим текст (для превью) — последовательно, чтобы не спамить
                    for (const filename of data.prompts) {
                        let preview = '';
                        try {
                            const r = await fetch('/ai_analysis/prompts/load/' + encodeURIComponent(filename));
                            const ld = await r.json();
                            if (ld.success && typeof ld.prompt === 'string') {
                                // Первый абзац (до пустой строки) или первые 200 символов
                                const para = ld.prompt.split(/\n\s*\n/)[0] || ld.prompt;
                                preview = para.trim().slice(0, 200);
                            }
                        } catch (_) {}

                        const item = document.createElement('div');
                        item.style.cssText = 'padding:10px; margin:6px 0; background:#f5f5f5; border-radius:6px; cursor:pointer;';
                        const title = document.createElement('div');
                        title.style.cssText = 'font-weight:600;';
                        title.textContent = filename;
                        const desc = document.createElement('div');
                        desc.style.cssText = 'font-size:12px; color:#555; margin-top:4px; white-space:pre-wrap;';
                        desc.textContent = preview || '(пусто)';
                        item.appendChild(title);
                        item.appendChild(desc);
                        item.addEventListener('click', async () => {
                            try {
                                const resp = await fetch('/ai_analysis/prompts/load/' + encodeURIComponent(filename));
                                const ld = await resp.json();
                                if (ld.success) {
                                    ragPromptText.value = ld.prompt || '';
                                    // Сохраняем загруженный промпт в localStorage
                                    try {
                                        localStorage.setItem('last_loaded_prompt', ld.prompt || '');
                                        localStorage.setItem('last_loaded_prompt_filename', filename);
                                    } catch (_) {}
                                    updateRagMetrics();
                                    autoResize(ragPromptText, 4);
                                    promptListModal.style.display = 'none';
                                } else {
                                    showMessage(ld.message || 'Не удалось загрузить промпт');
                                }
                            } catch (e) { showMessage('Ошибка загрузки: ' + e.message); }
                        });
                        promptList.appendChild(item);
                    }
                    promptListModal.style.display = 'block';
                } catch (e) { showMessage('Ошибка загрузки списка промптов: ' + e.message); }
            });
        }

        // Закрытие модалки списка промптов
        if (promptListClose) promptListClose.addEventListener('click', () => promptListModal.style.display = 'none');
        if (closePromptListBtn) closePromptListBtn.addEventListener('click', () => promptListModal.style.display = 'none');

})();
