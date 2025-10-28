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
    const aiResultError = document.getElementById('aiResultError');
    const aiResultErrorText = document.getElementById('aiResultErrorText');

    // Модал выбора промпта (переиспользуем существующий)
    const promptListModal = document.getElementById('promptListModal');
    const promptList = document.getElementById('promptList');
    const promptListClose = document.getElementById('promptListClose');
    const closePromptListBtn = document.getElementById('closePromptListBtn');

    // Состояние
    let models = [];
    let selectedModelId = null;
    let debounceTimer = null;
    let analysisTimerInterval = null;
    let analysisStartTime = null;

    function getSelectedFiles() {
        return window.getSelectedFiles ? window.getSelectedFiles() : [];
    }

    function showMessage(message) {
        if (window.showMessage) return window.showMessage(message);
        alert(message);
    }
    
    // Функция для запуска таймера анализа
    function startAnalysisTimer() {
        stopAnalysisTimer(); // Останавливаем предыдущий таймер, если есть
        analysisStartTime = Date.now();
        
        const updateTimer = () => {
            const elapsed = Math.floor((Date.now() - analysisStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            const timeStr = minutes > 0 
                ? `${minutes}:${seconds.toString().padStart(2, '0')}`
                : `${seconds} сек`;
            showMessage(`Выполняется AI анализ... (${timeStr})`);
        };
        
        // Обновляем сразу и затем каждую секунду
        updateTimer();
        analysisTimerInterval = setInterval(updateTimer, 1000);
    }
    
    // Функция для остановки таймера анализа
    function stopAnalysisTimer() {
        if (analysisTimerInterval) {
            clearInterval(analysisTimerInterval);
            analysisTimerInterval = null;
        }
        analysisStartTime = null;
    }
    
    // Функция для завершения анализа с показом итогового времени
    function finishAnalysisTimer(success = true) {
        if (analysisStartTime) {
            const elapsed = Math.floor((Date.now() - analysisStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            const timeStr = minutes > 0 
                ? `${minutes} мин ${seconds} сек`
                : `${seconds} сек`;
            
            stopAnalysisTimer();
            
            if (success) {
                showMessage(`Анализ выполнен успешно за ${timeStr}`);
            }
        }
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
                                        <div style="display:flex; gap:8px; align-items:center;">
                                            <label style="font-size:12px; color:#555;">Вход (за 1М): <input type="number" step="0.0001" min="0" data-price-in="${m.model_id}" value="${m.price_input_per_1m || 0}" style="width:120px;" /></label>
                                            <label style="font-size:12px; color:#555;">Выход (за 1М): <input type="number" step="0.0001" min="0" data-price-out="${m.model_id}" value="${m.price_output_per_1m || 0}" style="width:120px;" /></label>
                                            <label style="font-size:12px; color:#555;">Таймаут (сек): <input type="number" step="1" min="5" max="600" data-timeout="${m.model_id}" value="${m.timeout || 30}" style="width:80px;" title="Максимальное время ожидания ответа от модели" /></label>
                                            <button class="btn-delete-model" data-model-id="${m.model_id}" style="background:#dc3545; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px;" title="Удалить модель">🗑️ Удалить</button>
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

        // Обработчики изменения timeout - обновляем локально
        modelsList.querySelectorAll('input[data-timeout]').forEach(inp => {
            inp.addEventListener('input', (e) => {
                const modelId = e.target.getAttribute('data-timeout');
                const model = models.find(m => m.model_id === modelId);
                if (model) {
                    let timeout = parseInt(e.target.value) || 30;
                    // Ограничение диапазона 5-600 сек
                    if (timeout < 5) timeout = 5;
                    if (timeout > 600) timeout = 600;
                    model.timeout = timeout;
                }
            });
        });

        // Обработчики кнопок удаления модели
        modelsList.querySelectorAll('.btn-delete-model').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const modelId = e.target.getAttribute('data-model-id');
                const model = models.find(m => m.model_id === modelId);
                if (!model) return;

                // Проверка: нельзя удалить последнюю модель
                if (models.length === 1) {
                    alert('Нельзя удалить последнюю модель. Должна оставаться хотя бы одна модель.');
                    return;
                }

                // Подтверждение удаления
                if (!confirm(`Удалить модель "${model.display_name}"?\n\nВосстановить модель можно будет только вручную.`)) {
                    return;
                }

                // Отправка запроса на удаление
                try {
                    const response = await fetch(`/ai_rag/models/${encodeURIComponent(modelId)}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();

                    if (!response.ok) {
                        alert('Ошибка удаления: ' + (result.error || 'Неизвестная ошибка'));
                        return;
                    }

                    alert('Модель успешно удалена');

                    // Обновить список моделей
                    await loadModelsConfig();
                    renderModelsList();
                } catch (error) {
                    console.error('Ошибка при удалении модели:', error);
                    alert('Ошибка при удалении модели: ' + error.message);
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

        // Сохраняем состояние модала перед закрытием
        const wasModalOpen = ragModal.style.display === 'block';
        ragModal.style.display = 'none';
        
        // Запускаем таймер
        startAnalysisTimer();
        
        try {
            const res = await fetch('/ai_rag/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_paths: files,
                    prompt,
                    model_id: selectedModelId,
                    top_k: (ragDeepMode && ragDeepMode.checked) ? 8 : 5,
                    max_output_tokens: (ragDeepMode && ragDeepMode.checked) ? 2500 : 1500,
                    temperature: 0.3
                })
            });
            
            // Проверяем Content-Type перед парсингом JSON
            const contentType = res.headers.get('content-type');
            let data;
            
            if (!contentType || !contentType.includes('application/json')) {
                // Сервер вернул не-JSON (например, текст ошибки)
                stopAnalysisTimer();
                const text = await res.text();
                showMessage('Ошибка сервера: ' + text.substring(0, 200));
                if (wasModalOpen) {
                    ragModal.style.display = 'block';
                }
                return;
            }
            
            try {
                data = await res.json();
            } catch (jsonErr) {
                stopAnalysisTimer();
                const text = await res.text();
                showMessage('Ошибка парсинга ответа: ' + text.substring(0, 200));
                if (wasModalOpen) {
                    ragModal.style.display = 'block';
                }
                return;
            }
            if (data.success) {
                // Рендерим результат в HTML для красивого отображения
                const result = data.result;
                
                // Запрашиваем HTML версию
                try {
                    const htmlRes = await fetch('/ai_rag/render_html', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ result: result })
                    });
                    const htmlData = await htmlRes.json();
                    
                    if (htmlData.success && htmlData.html) {
                        // Создаем div для HTML контента
                        const resultDiv = document.createElement('div');
                        resultDiv.innerHTML = htmlData.html;
                        resultDiv.style.cssText = 'padding: 15px; max-height: 500px; overflow-y: auto; background: white; border: 1px solid #dee2e6; border-radius: 6px;';
                        
                        // Заменяем содержимое контейнера
                        const container = document.getElementById('aiResultContainer');
                        if (container) {
                            container.innerHTML = '';
                            container.appendChild(resultDiv);
                        }
                        
                        // Сохраняем исходные данные для кнопок
                        window._lastAnalysisResult = result;
                    } else {
                        // Fallback на plain text
                        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
                        aiResultText.value = text;
                    }
                } catch (htmlErr) {
                    console.error('Ошибка рендеринга HTML:', htmlErr);
                    // Fallback на plain text
                    const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
                    aiResultText.value = text;
                }
                
                aiResultModal.style.display = 'block';
                finishAnalysisTimer(true); // Показываем успешное завершение с итоговым временем
            } else {
                // При ошибке возвращаем модал обратно
                stopAnalysisTimer();
                showMessage(data.message || 'Ошибка анализа');
                if (wasModalOpen) {
                    ragModal.style.display = 'block';
                }
            }
        } catch (e) {
            // При ошибке сети возвращаем модал обратно
            stopAnalysisTimer();
            showMessage('Ошибка сети: ' + e.message);
            if (wasModalOpen) {
                ragModal.style.display = 'block';
            }
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
        
        // Загружаем курс USD/RUB из localStorage для корректного отображения рублей
        loadUsdRubRate();
        
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
    
    // Кнопка «Обновить модели» - открывает окно выбора новых моделей
    const modelRefreshBtn = document.getElementById('modelRefreshBtn');
    const addModelsModal = document.getElementById('addModelsModal');
    const addModelsClose = document.getElementById('addModelsClose');
    const addModelsCancelBtn = document.getElementById('addModelsCancelBtn');
    const addModelsConfirmBtn = document.getElementById('addModelsConfirmBtn');
    const newModelsList = document.getElementById('newModelsList');
    const addModelsStatus = document.getElementById('addModelsStatus');
    const addModelsStatusText = document.getElementById('addModelsStatusText');
    
    if (modelRefreshBtn && addModelsModal) {
        modelRefreshBtn.addEventListener('click', async () => {
            // Открыть модальное окно
            addModelsModal.style.display = 'block';
            addModelsStatus.style.display = 'none';
            newModelsList.innerHTML = '<p style="text-align: center; color: #777;">Загрузка списка доступных моделей...</p>';
            
            try {
                // Получить список всех доступных моделей из OpenAI
                const res = await fetch('/ai_rag/models/available', { method: 'GET' });
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
                }
                const data = await res.json();
                
                if (!data.success) {
                    throw new Error(data.message || 'Не удалось получить список моделей');
                }
                
                const availableModels = data.models || [];
                const currentModels = models.map(m => m.model_id);
                
                // Фильтруем - показываем только те, которых еще нет
                const newModels = availableModels.filter(m => !currentModels.includes(m.model_id));
                
                if (newModels.length === 0) {
                    newModelsList.innerHTML = '<p style="text-align: center; color: #777;">Все доступные модели уже добавлены</p>';
                } else {
                    // Рендерим список с чекбоксами
                    let html = '';
                    newModels.forEach(m => {
                        html += `
                            <div style="border: 1px solid #ddd; border-radius: 6px; padding: 10px; margin-bottom: 10px;">
                                <label style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer;">
                                    <input type="checkbox" class="new-model-checkbox" data-model-id="${m.model_id}" />
                                    <div style="flex: 1;">
                                        <div><strong>${m.display_name || m.model_id}</strong></div>
                                        <div style="font-size: 12px; color: #666; margin-top: 4px;">
                                            ID: ${m.model_id}
                                        </div>
                                        ${m.context_window_tokens ? `<div style="font-size: 12px; color: #666;">Контекст: ${Number(m.context_window_tokens).toLocaleString()} токенов</div>` : ''}
                                    </div>
                                </label>
                            </div>
                        `;
                    });
                    newModelsList.innerHTML = html;
                }
            } catch (e) {
                console.error('Ошибка при загрузке моделей:', e);
                newModelsList.innerHTML = `<p style="text-align: center; color: #d32f2f;">Ошибка: ${e.message}</p>`;
            }
        });
        
        // Закрытие окна
        if (addModelsClose) {
            addModelsClose.addEventListener('click', () => addModelsModal.style.display = 'none');
        }
        if (addModelsCancelBtn) {
            addModelsCancelBtn.addEventListener('click', () => addModelsModal.style.display = 'none');
        }
        
        // Добавление выбранных моделей
        if (addModelsConfirmBtn) {
            addModelsConfirmBtn.addEventListener('click', async () => {
                const checkboxes = newModelsList.querySelectorAll('.new-model-checkbox:checked');
                const selectedIds = Array.from(checkboxes).map(cb => cb.getAttribute('data-model-id'));
                
                if (selectedIds.length === 0) {
                    alert('Выберите хотя бы одну модель');
                    return;
                }
                
                // Отправить запрос на добавление
                try {
                    addModelsStatus.style.display = 'block';
                    addModelsStatusText.textContent = 'Добавление моделей...';
                    
                    const res = await fetch('/ai_rag/models/add', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ model_ids: selectedIds })
                    });
                    
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
                    }
                    
                    const data = await res.json();
                    
                    if (!data.success) {
                        throw new Error(data.message || 'Не удалось добавить модели');
                    }
                    
                    addModelsStatusText.textContent = `Успешно добавлено моделей: ${data.added || 0}`;
                    
                    // Обновить список моделей
                    await loadModelsConfig();
                    renderModelsList();
                    
                    // Закрыть окно через 1.5 сек
                    setTimeout(() => {
                        addModelsModal.style.display = 'none';
                    }, 1500);
                    
                } catch (e) {
                    console.error('Ошибка при добавлении моделей:', e);
                    addModelsStatusText.textContent = `Ошибка: ${e.message}`;
                    addModelsStatus.style.background = '#ffebee';
                }
            });
        }
    }
    
    if (ragStartBtn) {
        ragStartBtn.addEventListener('click', startAnalysis);
    }
    
    // Обработчики кнопок модала результата
    if (aiResultClose) {
        aiResultClose.addEventListener('click', () => aiResultModal.style.display = 'none');
    }
    
    const closeResultBtn = document.getElementById('closeResultBtn');
    const copyResultBtn = document.getElementById('copyResultBtn');
    const saveResultBtn = document.getElementById('saveResultBtn');
    const openNewTabBtn = document.getElementById('openNewTabBtn');
    const exportDocxBtn = document.getElementById('exportDocxBtn');
    
    if (closeResultBtn) {
        closeResultBtn.addEventListener('click', () => aiResultModal.style.display = 'none');
    }
    
    if (copyResultBtn) {
        copyResultBtn.addEventListener('click', function() {
            // Получаем текст из сохраненного результата или из textarea
            let text = '';
            
            if (window._lastAnalysisResult && window._lastAnalysisResult.answer) {
                // Используем исходный Markdown текст
                const result = window._lastAnalysisResult;
                text = `Модель: ${result.model}\n`;
                text += `Стоимость: $${result.cost?.total || 0}\n`;
                if (result.cost?.total_rub) {
                    text += `В рублях: ₽${result.cost.total_rub} (по курсу $${result.cost.usd_to_rub_rate})\n`;
                }
                text += `Токены: ${result.usage?.total_tokens || 0}\n`;
                text += `\n${'='.repeat(80)}\n\n`;
                text += result.answer;
            } else {
                text = aiResultText.value;
            }
            
            if (!text) {
                showMessage('Нет текста для копирования');
                return;
            }
            
            navigator.clipboard.writeText(text)
                .then(() => showMessage('Результат скопирован в буфер обмена'))
                .catch(error => showMessage('Ошибка копирования: ' + error));
        });
    }
    
    if (saveResultBtn) {
        saveResultBtn.addEventListener('click', function() {
            // Получаем текст из сохраненного результата или из textarea
            let text = '';
            
            if (window._lastAnalysisResult && window._lastAnalysisResult.answer) {
                // Форматируем для сохранения в файл
                const result = window._lastAnalysisResult;
                text = `${'='.repeat(80)}\n`;
                text += `AI АНАЛИЗ\n`;
                text += `${'='.repeat(80)}\n`;
                text += `Модель: ${result.model}\n`;
                text += `Стоимость: $${result.cost?.total || 0} (вход: $${result.cost?.input || 0}, выход: $${result.cost?.output || 0})\n`;
                if (result.cost?.total_rub) {
                    text += `В рублях: ₽${result.cost.total_rub} (вход: ₽${result.cost.input_rub}, выход: ₽${result.cost.output_rub}) по курсу $${result.cost.usd_to_rub_rate}\n`;
                }
                text += `Токены: ${result.usage?.total_tokens || 0} (вход: ${result.usage?.input_tokens || 0}, выход: ${result.usage?.output_tokens || 0})\n`;
                text += `${'='.repeat(80)}\n\n`;
                text += result.answer;
            } else {
                text = aiResultText.value;
            }
            if (!text) {
                showMessage('Нет текста для сохранения');
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
            showMessage(`Результат сохранён: ${filename}`);
        });
    }
    
    // Кнопка "Открыть в новой вкладке"
    if (openNewTabBtn) {
        openNewTabBtn.addEventListener('click', async function() {
            if (!window._lastAnalysisResult || !window._lastAnalysisResult.answer) {
                showMessage('Нет результата для отображения');
                return;
            }
            
            try {
                // Запрашиваем HTML-версию для новой вкладки
                const res = await fetch('/ai_rag/render_html', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ result: window._lastAnalysisResult })
                });
                
                const data = await res.json();
                
                if (data.success && data.html) {
                    // Открываем новое окно с полным HTML
                    const newWindow = window.open('', '_blank');
                    if (newWindow) {
                        newWindow.document.write(`
                            <!DOCTYPE html>
                            <html lang="ru">
                            <head>
                                <meta charset="UTF-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                <title>Результат AI анализа</title>
                                <style>
                                    body {
                                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                                        max-width: 900px;
                                        margin: 40px auto;
                                        padding: 20px;
                                        background: #f5f5f5;
                                    }
                                    .content {
                                        background: white;
                                        padding: 30px;
                                        border-radius: 8px;
                                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                                    }
                                    @media print {
                                        body { background: white; margin: 0; }
                                        .content { box-shadow: none; padding: 0; }
                                    }
                                </style>
                            </head>
                            <body>
                                <div class="content">
                                    ${data.html}
                                </div>
                            </body>
                            </html>
                        `);
                        newWindow.document.close();
                        showMessage('Результат открыт в новой вкладке');
                    } else {
                        showMessage('Не удалось открыть новое окно. Проверьте настройки браузера.');
                    }
                } else {
                    showMessage(data.message || 'Ошибка получения HTML');
                }
            } catch (err) {
                showMessage('Ошибка открытия в новой вкладке: ' + err.message);
            }
        });
    }
    
    // Кнопка "Сохранить как DOCX"
    if (exportDocxBtn) {
        exportDocxBtn.addEventListener('click', async function() {
            if (!window._lastAnalysisResult || !window._lastAnalysisResult.answer) {
                showMessage('Нет результата для экспорта');
                return;
            }
            
            try {
                showMessage('Создание DOCX файла...');
                
                const res = await fetch('/ai_rag/export_docx', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ result: window._lastAnalysisResult })
                });
                
                if (res.ok) {
                    // Получаем blob для скачивания
                    const blob = await res.blob();
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                    const filename = `ai_analysis_${timestamp}.docx`;
                    
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    
                    showMessage(`DOCX файл сохранён: ${filename}`);
                } else {
                    const errorText = await res.text();
                    showMessage('Ошибка экспорта: ' + errorText.substring(0, 100));
                }
            } catch (err) {
                showMessage('Ошибка экспорта DOCX: ' + err.message);
            }
        });
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
