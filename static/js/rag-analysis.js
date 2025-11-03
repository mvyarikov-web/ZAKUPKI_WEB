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
    // Глубокий анализ теперь всегда включён (чекбокс удалён)
    const ragDeepMode = null;
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

    // Параметры Search API
    const searchApiParams = document.getElementById('searchApiParams');
    const searchMaxResults = document.getElementById('searchMaxResults');
    const searchDomainFilter = document.getElementById('searchDomainFilter');
    const searchRecency = document.getElementById('searchRecency');
    const searchAfterDate = document.getElementById('searchAfterDate');
    const searchBeforeDate = document.getElementById('searchBeforeDate');
    const searchCountry = document.getElementById('searchCountry');
    const searchMaxTokens = document.getElementById('searchMaxTokens');
    const searchMaxTokensValue = document.getElementById('searchMaxTokensValue');
    
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

    // Элементы прогресс-бара
    const ragProgressBar = document.getElementById('ragAnalysisProgress');
    const ragProgressFill = document.getElementById('ragAnalysisFill');
    const ragProgressTime = document.getElementById('ragAnalysisTime');
    const ragProgressStatus = document.getElementById('ragAnalysisStatus');

    function getSelectedFiles() {
        return window.getSelectedFiles ? window.getSelectedFiles() : [];
    }

    // Удалена локальная функция showMessage - используем MessageManager
    // Все сообщения показываются в контексте ragModal
    
    // Функция форматирования времени
    function formatElapsedTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        if (minutes > 0) {
            return `${minutes} мин ${secs} сек`;
        }
        return `${secs} сек`;
    }
    
    // Функция для запуска таймера и прогресс-бара анализа
    function startAnalysisTimer() {
        stopAnalysisTimer(); // Останавливаем предыдущий таймер, если есть
        analysisStartTime = Date.now();
        
        // Показываем прогресс-бар
        if (ragProgressBar) {
            ragProgressBar.style.display = 'block';
            ragProgressBar.style.visibility = 'visible';
        }
        
        // Устанавливаем начальное состояние (10% - начало)
        if (ragProgressFill) {
            ragProgressFill.style.width = '10%';
            ragProgressFill.classList.remove('completed');
        }
        
        if (ragProgressStatus) {
            ragProgressStatus.textContent = '⏳ Выполняется AI анализ...';
        }
        
        const updateTimer = () => {
            const elapsed = Math.floor((Date.now() - analysisStartTime) / 1000);
            if (ragProgressTime) {
                ragProgressTime.textContent = formatElapsedTime(elapsed);
            }
            
            // Плавно увеличиваем прогресс от 10% до 90% (оставляем 10% на финализацию)
            // За каждые 5 секунд +10%
            const progress = Math.min(90, 10 + Math.floor(elapsed / 5) * 10);
            if (ragProgressFill) {
                ragProgressFill.style.width = `${progress}%`;
            }
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
            const timeStr = formatElapsedTime(elapsed);
            
            stopAnalysisTimer();
            
            // Устанавливаем прогресс на 100% и показываем финальный статус
            if (ragProgressFill) {
                ragProgressFill.style.width = '100%';
                ragProgressFill.classList.add('completed');
            }
            
            if (ragProgressTime) {
                ragProgressTime.textContent = timeStr;
            }
            
            if (ragProgressStatus) {
                if (success) {
                    ragProgressStatus.textContent = '✅ Анализ выполнен успешно';
                    ragProgressStatus.style.color = '#4CAF50';
                } else {
                    ragProgressStatus.textContent = '❌ Анализ завершен с ошибкой';
                    ragProgressStatus.style.color = '#f44336';
                }
            }
            
            // Скрываем сообщение с таймером (оно больше не нужно - есть прогресс-бар)
            MessageManager.hide('ragModal');
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

                // Восстановление последней выбранной модели из localStorage
                const savedModelId = localStorage.getItem('rag_selected_model');
                const savedSearchStates = JSON.parse(localStorage.getItem('rag_search_enabled') || '{}');
                const savedNewRequestStates = JSON.parse(localStorage.getItem('rag_new_request') || '{}');

                // Восстанавливаем флаги search_enabled и new_request_enabled для каждой модели
                models.forEach(m => {
                    if (savedSearchStates[m.model_id] !== undefined) {
                        m.search_enabled = savedSearchStates[m.model_id];
                    }
                    if (savedNewRequestStates[m.model_id] !== undefined) {
                        m.new_request_enabled = savedNewRequestStates[m.model_id];
                    }
                });
                
                // Выбираем модель: сохранённая → дефолтная → первая
                if (savedModelId && models.find(m => m.model_id === savedModelId)) {
                    selectedModelId = savedModelId;
                } else {
                    selectedModelId = data.default_model || (models[0] && models[0].model_id) || null;
                }
                
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
        let modelName = m ? m.display_name : 'не выбрана';
        // Добавляем "+ Search" если включён режим поиска
        if (m && m.search_enabled) {
            modelName += ' + Search';
        }
        ragCurrentModel.textContent = `Модель: ${modelName}`;
    }

    // Функция для раскрытия/скрытия параметров модели (экспорт в window для доступа из HTML)
    window.toggleModelParams = function(expandedId) {
        const expandedRow = document.getElementById(expandedId);
        if (!expandedRow) return;
        
        if (expandedRow.style.display === 'none') {
            expandedRow.style.display = '';
        } else {
            expandedRow.style.display = 'none';
        }
    }

    function renderModelsList() {
        if (!modelsList) return;
        if (!models || models.length === 0) {
            modelsList.innerHTML = '<tr><td colspan="6" style="padding: 40px; text-align: center; color: #9ca3af;">Модели не загружены</td></tr>';
            return;
        }

        let html = '';
        models.forEach((m, index) => {
            const checked = m.model_id === selectedModelId ? 'checked' : '';
            const isEnabled = m.enabled !== false;
            const statusBadge = isEnabled 
                ? '<span style="display:inline-block; padding:3px 8px; background:#d1fae5; color:#065f46; border-radius:12px; font-size:11px; font-weight:600;">✓ Активна</span>' 
                : '<span style="display:inline-block; padding:3px 8px; background:#fee2e2; color:#991b1b; border-radius:12px; font-size:11px; font-weight:600;">✗ Неактивна</span>';
            
            const contextInfo = `${Number(m.context_window_tokens || 0).toLocaleString()}`;
            const isSearchMode = m.supports_search && (m.search_enabled || false);
            const rowBg = index % 2 === 0 ? '#ffffff' : '#f9fafb';
            const expandedId = `expanded-${m.model_id}`;
            
            // Основная строка таблицы
            html += `
                <tr style="background: ${rowBg}; border-bottom: 1px solid #e5e7eb; transition: background 0.2s;" 
                    onmouseover="this.style.background='#f3f4f6'" 
                    onmouseout="this.style.background='${rowBg}'">
                    <!-- Колонка выбора -->
                    <td style="padding: 12px 15px; text-align: center; vertical-align: middle;">
                        <input type="radio" 
                               name="rag-model" 
                               value="${m.model_id}" 
                               ${checked} 
                               style="width: 18px; height: 18px; cursor: pointer;" 
                               title="Выбрать эту модель" />
                    </td>
                    
                    <!-- Колонка модели (название + описание) -->
                    <td style="padding: 12px 15px; vertical-align: middle;">
                        <div style="font-weight: 600; font-size: 14px; color: #111827; margin-bottom: 4px;">
                            ${m.display_name}
                        </div>
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">
                            <code style="background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 11px;">${m.model_id}</code>
                        </div>
                        <div style="font-size: 12px; color: #6b7280; line-height: 1.4;">
                            ${m.description || 'Описание отсутствует'}
                        </div>
            `;
            
            // Если модель поддерживает поиск, показываем чекбоксы
            if (m.supports_search) {
                const searchEnabled = m.search_enabled || false;
                const newRequestEnabled = m.new_request_enabled || false;
                html += `
                        <div style="margin-top: 8px; padding: 8px; background: #ecfdf5; border-radius: 6px; border: 1px solid #a7f3d0;">
                            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #065f46;">
                                <input type="checkbox" 
                                       data-search-toggle="${m.model_id}" 
                                       ${searchEnabled ? 'checked' : ''}
                                       style="width: 16px; height: 16px; cursor: pointer;" />
                                <span style="font-weight: 600;">🌐 С поиском в интернете</span>
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #047857; margin-top: 6px;">
                                <input type="checkbox" 
                                       data-new-request-toggle="${m.model_id}" 
                                       ${newRequestEnabled ? 'checked' : ''}
                                       style="width: 16px; height: 16px; cursor: pointer;" />
                                <span style="font-weight: 600;">🔄 Новый запрос (очистить контекст)</span>
                            </label>
                        </div>
                `;
            }
            
            html += `
                    </td>
                    
                    <!-- Колонка статуса -->
                    <td style="padding: 12px 15px; text-align: center; vertical-align: middle;">
                        ${statusBadge}
                    </td>
                    
                    <!-- Колонка контекста -->
                    <td style="padding: 12px 15px; text-align: right; vertical-align: middle;">
                        <div style="font-weight: 600; font-size: 14px; color: #374151;">
                            ${contextInfo}
                        </div>
                        <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">
                            токенов
                        </div>
                    </td>
                    
                    <!-- Колонка параметров (кнопка раскрытия) -->
                    <td style="padding: 12px 15px; text-align: center; vertical-align: middle;">
                        <button onclick="toggleModelParams('${expandedId}')" 
                                style="background: #95a5a6; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: background 0.2s;"
                                onmouseover="this.style.background='#7f8c8d'" 
                                onmouseout="this.style.background='#95a5a6'"
                                title="Показать/скрыть параметры">
                            <span style="filter: hue-rotate(200deg) saturate(2);">⚙️</span> Настройки
                        </button>
                    </td>
                    
                    <!-- Колонка действий -->
                    <td style="padding: 12px 15px; text-align: center; vertical-align: middle;">
                        <button class="btn-delete-model" 
                                data-model-id="${m.model_id}" 
                                style="background: #9b2d30; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: background 0.2s;"
                                onmouseover="this.style.background='#7a2326'" 
                                onmouseout="this.style.background='#9b2d30'"
                                title="Удалить модель">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
            
            // Расширенная строка с параметрами (скрытая по умолчанию)
            html += `
                <tr id="${expandedId}" style="display: none; background: #f9fafb;">
                    <td colspan="6" style="padding: 20px 30px;">
                        <div style="background: white; border-radius: 8px; padding: 20px; border: 2px solid #e5e7eb;">
                            <div style="font-weight: 600; font-size: 14px; color: #111827; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #e5e7eb;">
                                ⚙️ Параметры модели: ${m.display_name}
                            </div>
                            
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
            `;
            
            // Выбор полей в зависимости от режима поиска
            if (isSearchMode) {
                // Режим поиска: стоимость за запросы
                html += `
                                <div>
                                    <label style="display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; font-weight: 500;">
                                        💰 Стоимость 1000 запросов ($)
                                    </label>
                                    <input type="number" 
                                           step="0.01" 
                                           min="0" 
                                           data-price-requests="${m.model_id}" 
                                           value="${m.price_per_1000_requests || 5.0}" 
                                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;" 
                                           placeholder="5.00" />
                                </div>
                `;
            } else {
                // Обычный режим: стоимость токенов
                html += `
                                <div>
                                    <label style="display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; font-weight: 500;">
                                        📥 Стоимость входа (за 1М токенов, $)
                                    </label>
                                    <input type="number" 
                                           step="0.0001" 
                                           min="0" 
                                           data-price-in="${m.model_id}" 
                                           value="${m.price_input_per_1m || 0}" 
                                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;" 
                                           placeholder="0.0000" />
                                </div>
                                
                                <div>
                                    <label style="display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; font-weight: 500;">
                                        📤 Стоимость выхода (за 1М токенов, $)
                                    </label>
                                    <input type="number" 
                                           step="0.0001" 
                                           min="0" 
                                           data-price-out="${m.model_id}" 
                                           value="${m.price_output_per_1m || 0}" 
                                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;" 
                                           placeholder="0.0000" />
                                </div>
                `;
            }
            
            html += `
                                <div>
                                    <label style="display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; font-weight: 500;">
                                        ⏱️ Таймаут (секунд)
                                    </label>
                                    <input type="number" 
                                           step="1" 
                                           min="5" 
                                           max="600" 
                                           data-timeout="${m.model_id}" 
                                           value="${m.timeout || 30}" 
                                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;" 
                                           title="Максимальное время ожидания ответа от модели" 
                                           placeholder="30" />
                                </div>
                            </div>
                            
                            <div style="margin-top: 12px; padding: 10px; background: #eff6ff; border-radius: 6px; border-left: 3px solid #3b82f6;">
                                <span style="font-size: 12px; color: #1e40af;">
                                    💡 <strong>Подсказка:</strong> Измените параметры и нажмите «Сохранить изменения» внизу окна.
                                </span>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        });
        
        modelsList.innerHTML = html;

        // Обработчики выбора модели
        modelsList.querySelectorAll('input[name="rag-model"]').forEach(r => {
            r.addEventListener('change', (e) => {
                selectedModelId = e.target.value;
                // Сохраняем выбранную модель в localStorage
                localStorage.setItem('rag_selected_model', selectedModelId);
                updateCurrentModelLabel();
                updateRagMetrics();
                toggleSearchApiParams();
            });
        });
        
        // Обработчики чекбоксов "С поиском в интернете"
        modelsList.querySelectorAll('input[data-search-toggle]').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const modelId = e.target.getAttribute('data-search-toggle');
                const model = models.find(m => m.model_id === modelId);
                if (model) {
                    model.search_enabled = e.target.checked;
                    
                    // Сохраняем состояния search_enabled в localStorage
                    const savedSearchStates = JSON.parse(localStorage.getItem('rag_search_enabled') || '{}');
                    savedSearchStates[modelId] = e.target.checked;
                    localStorage.setItem('rag_search_enabled', JSON.stringify(savedSearchStates));
                    
                    // Перерисовываем список моделей для обновления полей тарификации
                    renderModelsList();
                    // Обновляем метрики
                    updateRagMetrics();
                    // Обновляем видимость параметров поиска
                    toggleSearchApiParams();
                }
            });
        });

        // Обработчики чекбоксов "Новый запрос"
        modelsList.querySelectorAll('input[data-new-request-toggle]').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const modelId = e.target.getAttribute('data-new-request-toggle');
                const model = models.find(m => m.model_id === modelId);
                if (model) {
                    model.new_request_enabled = e.target.checked;

                    // Сохраняем состояния new_request_enabled в localStorage
                    const savedNewRequestStates = JSON.parse(localStorage.getItem('rag_new_request') || '{}');
                    savedNewRequestStates[modelId] = e.target.checked;
                    localStorage.setItem('rag_new_request', JSON.stringify(savedNewRequestStates));
                }
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
                e.preventDefault();
                e.stopPropagation();
                const modelId = e.currentTarget.getAttribute('data-model-id');
                const model = models.find(m => m.model_id === modelId);
                if (!model) return;

                // Проверка: нельзя удалить последнюю модель
                if (models.length === 1) {
                    MessageManager.warning('Нельзя удалить последнюю модель. Должна оставаться хотя бы одна модель.', 'ragModal', 0);
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
                        MessageManager.error('Ошибка удаления: ' + (result.error || 'Неизвестная ошибка'), 'ragModal');
                        return;
                    }

                    MessageManager.success('Модель успешно удалена', 'ragModal');

                    // Обновить список моделей
                    await loadModels();
                    renderModelsList();
                } catch (error) {
                    console.error('Ошибка при удалении модели:', error);
                    MessageManager.error('Ошибка при удалении модели: ' + error.message, 'ragModal');
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
    
    // Показ/скрытие параметров поиска
    function toggleSearchApiParams() {
        if (!searchApiParams) return;
        
        const model = models.find(m => m.model_id === selectedModelId);
        // Показываем параметры если модель поддерживает поиск И режим поиска включен
        if (model && model.supports_search && model.search_enabled) {
            searchApiParams.style.display = 'block';
            
            // Загружаем сохранённые значения параметров (из localStorage либо из модели)
            const lsKey = `rag_search_params_${model.model_id}`;
            let params = null;
            try {
                params = JSON.parse(localStorage.getItem(lsKey) || 'null');
            } catch (e) { params = null; }
            if (!params && model.search_params) params = model.search_params;
            if (params) {
                if (searchMaxResults) searchMaxResults.value = params.max_results || 10;
                if (searchDomainFilter) {
                    // Преобразуем массив в строку через запятую
                    const domains = Array.isArray(params.search_domain_filter) ? params.search_domain_filter.join(', ') : (params.search_domain_filter || '');
                    searchDomainFilter.value = domains;
                }
                if (searchRecency) searchRecency.value = params.search_recency_filter || '';
                if (searchAfterDate) searchAfterDate.value = params.search_after_date || '';
                if (searchBeforeDate) searchBeforeDate.value = params.search_before_date || '';
                if (searchCountry) searchCountry.value = params.country || '';
                if (searchMaxTokens) {
                    searchMaxTokens.value = params.max_tokens_per_page || 1024;
                    if (searchMaxTokensValue) searchMaxTokensValue.textContent = searchMaxTokens.value;
                }
            }

            // Навешиваем обработчики для автосохранения в localStorage
            const persistParams = () => {
                const p = {
                    max_results: searchMaxResults ? Number(searchMaxResults.value) || 10 : 10,
                    search_domain_filter: searchDomainFilter && searchDomainFilter.value ? searchDomainFilter.value.split(',').map(s => s.trim()).filter(Boolean) : [],
                    search_recency_filter: searchRecency ? searchRecency.value || '' : '',
                    search_after_date: searchAfterDate ? searchAfterDate.value || '' : '',
                    search_before_date: searchBeforeDate ? searchBeforeDate.value || '' : '',
                    country: searchCountry ? searchCountry.value || '' : '',
                    max_tokens_per_page: searchMaxTokens ? Number(searchMaxTokens.value) || 1024 : 1024
                };
                localStorage.setItem(lsKey, JSON.stringify(p));
            };
            [searchMaxResults, searchDomainFilter, searchRecency, searchAfterDate, searchBeforeDate, searchCountry, searchMaxTokens]
                .filter(Boolean)
                .forEach(inp => inp.addEventListener('input', persistParams));
        } else {
            searchApiParams.style.display = 'none';
        }
    }

    async function saveSearchApiParams(modelId, searchParams) {
        // Сохраняем параметры поиска для модели
        try {
            const response = await fetch('/ai_rag/models/search_params', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: modelId,
                    search_params: searchParams
                })
            });
            
            if (response.ok) {
                // Обновляем локальную копию модели
                const model = models.find(m => m.model_id === modelId);
                if (model) {
                    model.search_params = searchParams;
                }
            }
        } catch (error) {
            console.error('Ошибка при сохранении параметров поиска:', error);
        }
    }

    async function saveModelPrices() {
        // Собираем значения из инпутов
        const inputsIn = modelsList.querySelectorAll('input[data-price-in]');
        const inputsOut = modelsList.querySelectorAll('input[data-price-out]');
        const inputsRequests = modelsList.querySelectorAll('input[data-price-requests]');
        const inputsTimeout = modelsList.querySelectorAll('input[data-timeout]');
        const toSave = [];

        // Обрабатываем модели с токенами
        inputsIn.forEach(inp => {
            const id = inp.getAttribute('data-price-in');
            const model = models.find(m => m.model_id === id);
            const valIn = parseFloat(inp.value) || 0;
            const outInp = modelsList.querySelector(`input[data-price-out="${id}"]`);
            const valOut = outInp ? (parseFloat(outInp.value) || 0) : 0;
            const timeoutInp = modelsList.querySelector(`input[data-timeout="${id}"]`);
            const timeout = timeoutInp ? (parseInt(timeoutInp.value) || 30) : 30;
            const item = { 
                model_id: id, 
                price_input_per_1m: valIn, 
                price_output_per_1m: valOut,
                timeout: timeout
            };
            // Если модель поддерживает поиск, добавляем флаг search_enabled
            if (model && model.supports_search) {
                item.search_enabled = model.search_enabled || false;
            }
            toSave.push(item);
        });
        
        // Обрабатываем модели с запросами (режим поиска)
        inputsRequests.forEach(inp => {
            const id = inp.getAttribute('data-price-requests');
            const model = models.find(m => m.model_id === id);
            const pricePerRequests = parseFloat(inp.value) || 5.0;
            const timeoutInp = modelsList.querySelector(`input[data-timeout="${id}"]`);
            const timeout = timeoutInp ? (parseInt(timeoutInp.value) || 30) : 30;
            const item = {
                model_id: id,
                price_per_1000_requests: pricePerRequests,
                timeout: timeout
            };
            // Если модель поддерживает поиск, добавляем флаг search_enabled
            if (model && model.supports_search) {
                item.search_enabled = model.search_enabled || false;
            }
            toSave.push(item);
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

        MessageManager.success('Настройки сохранены', 'ragModal');
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
        let modelName = m ? m.display_name : '—';
        // Добавляем "+ Search" если включён режим поиска
        if (m && m.search_enabled) {
            modelName += ' + Search';
        }
        return {
            inPrice: m ? (m.price_input_per_1m || 0) : 0,
            outPrice: m ? (m.price_output_per_1m || 0) : 0,
            name: modelName
        };
    }

    // Функция для проверки наличия битых символов (кракозябр)
    function detectMojibake(text) {
        // Паттерны для обнаружения битого текста (неправильная кодировка)
        const mojibakePattern = /[–∂—ë–a—ã–μ–æ–ø–μ—Ä–∞—Ü–∏–∏—Ç–æ–a—å–∫–æ–Ω–∞—ç—Ç–∞–ø–μ–∏–Ω–¥–μ–∫—Å–∞—Ü–∏–∏–Ω–μ–≤–ú–∏–Ω–∏–o–∞–a—å–Ω—ã–μ–∏–∑–o–μ–Ω–μ–Ω–∏—è–ü—É–±–a–∏—á–Ω—ã]{8,}/g;
        const garbagePattern = /[–]{2,}[∂—ë]+[–]{2,}|[–∂—ë–a—ã–μ–æ–ø]{10,}/g;
        
        return mojibakePattern.test(text) || garbagePattern.test(text);
    }
    
    // Функция для подсчёта битых символов
    function countMojibakeChars(text) {
        const mojibakeChars = '–∂—ë–a—ã–μ–æ–ø–μ—Ä–∞—Ü–∏–∏—Ç–æ–a—å–∫–æ–Ω–∞—ç—Ç–∞–ø–μ–∏–Ω–¥–μ–∫—Å–∞—Ü–∏–∏–Ω–μ–≤–ú–∏–Ω–∏–o–∞–a—å–Ω—ã–μ–∏–∑–o–μ–Ω–μ–Ω–∏—è–ü—É–±–a–∏—á–Ω—ã';
        let count = 0;
        
        for (let i = 0; i < text.length; i++) {
            if (mojibakeChars.includes(text[i])) {
                count++;
            }
        }
        
        return count;
    }
    
    /**
     * Показывает сообщение о качестве текста (mojibake) в message-area
     * @param {number} percent - Процент нечитаемых символов
     * @param {number} count - Количество нечитаемых символов
     * @param {number} total - Общее количество символов
     */
    function showMojibakeMessage(percent, count, total) {
        const messageArea = document.getElementById('rag-message-area');
        if (!messageArea) {
            console.warn('[showMojibakeMessage] Не найдена область rag-message-area');
            return;
        }

        // Скрываем сообщение, если нет нечитаемых символов
        if (count === 0) {
            messageArea.style.display = 'none';
            return;
        }

        const percentNum = parseFloat(percent);
        let messageType = '';
        let icon = '';
        let text = '';

        if (percentNum < 5) {
            // Зелёное сообщение: качество отличное
            messageType = 'success';
            icon = '✅';
            text = `Качество текста отличное, нечитаемых символов: ${percent}% (${count.toLocaleString('ru-RU')} из ${total.toLocaleString('ru-RU')})`;
        } else if (percentNum >= 5 && percentNum < 25) {
            // Жёлтое предупреждение: рекомендуется оптимизация
            messageType = 'warning';
            icon = '⚠️';
            text = `Обнаружено ${percent}% нечитаемых символов (${count.toLocaleString('ru-RU')} из ${total.toLocaleString('ru-RU')}). Рекомендация: используйте кнопку "⚡ Оптимизировать текст" для улучшения качества анализа`;
        } else {
            // Красное предупреждение: критически много
            messageType = 'error';
            icon = '❌';
            text = `Критически много нечитаемых символов (${percent}%, ${count.toLocaleString('ru-RU')} из ${total.toLocaleString('ru-RU')}). Настоятельно рекомендуется очистка текста с помощью кнопки "⚡ Оптимизировать текст" перед анализом`;
        }

        // Очищаем предыдущее содержимое
        messageArea.innerHTML = '';
        
        // Создаём текстовый элемент
        const textSpan = document.createElement('span');
        textSpan.style.cssText = 'white-space: pre-wrap; flex: 1;';
        textSpan.textContent = `${icon} ${text}`;
        
        // Создаём кнопку закрытия
        const closeBtn = document.createElement('span');
        closeBtn.textContent = '×';
        closeBtn.style.cssText = 'cursor: pointer; font-size: 24px; font-weight: bold; margin-left: 15px; opacity: 0.7; flex-shrink: 0; line-height: 1;';
        closeBtn.title = 'Закрыть сообщение';
        closeBtn.onclick = () => {
            messageArea.style.display = 'none';
        };
        
        // Добавляем элементы
        messageArea.appendChild(textSpan);
        messageArea.appendChild(closeBtn);
        messageArea.style.display = 'flex';
        messageArea.style.alignItems = 'flex-start';
        messageArea.style.justifyContent = 'space-between';
        
        // Устанавливаем класс для стиля
        messageArea.className = 'modal-message-area ' + messageType;
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
            // Глубокий анализ всегда включён
            const deep = true;
            
            // Для моделей o1 и deepseek-reasoner увеличиваем оценку выходных токенов (длинные рассуждения)
            let expectedOutput;
            if (selectedModelId && (selectedModelId.startsWith('o1') || selectedModelId === 'deepseek-reasoner')) {
                expectedOutput = 8000;
            } else {
                expectedOutput = 2500;
            }
            
            const totalTokens = inputTokens + expectedOutput;

            const model = models.find(m => m.model_id === selectedModelId);
            const isSearchMode = model && model.supports_search && model.search_enabled;
            
            let info = '';
            
            if (isSearchMode) {
                // Режим поиска: показываем "Model + Search"
                info = `Модель: ${model.display_name} + Search. Символы: промпт ${promptChars.toLocaleString()}, документы ${docsChars.toLocaleString()}, всего ${totalChars.toLocaleString()}.`;
                
                // Стоимость по запросам
                const pricePerRequest = model.price_per_1000_requests || 5.0;
                const estimatedRequests = 1; // За один анализ считаем 1 запрос
                const totalCost = (estimatedRequests / 1000) * pricePerRequest;
                
                info += ` Стоимость (оценка): $${totalCost.toFixed(4)} за ${estimatedRequests} запрос`;
                
                // Добавляем пересчёт в рубли
                const rate = getUsdRubRate();
                if (rate > 0) {
                    const rubTotal = totalCost * rate;
                    info += ` (${rubTotal.toFixed(2)}₽)`;
                }
                info += '.';
            } else {
                // Обычный режим: токены
                const { inPrice, outPrice, name } = getSelectedModelPrices();
                info = `Модель: ${name}. Символы: промпт ${promptChars.toLocaleString()}, документы ${docsChars.toLocaleString()}, всего ${totalChars.toLocaleString()}. Токены (оценка): вход ${inputTokens.toLocaleString()}, выход ${expectedOutput.toLocaleString()}, всего ${totalTokens.toLocaleString()}.`;

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
            }

            // Проверяем наличие битых символов и показываем в message-area
            const fullText = prompt + '\n\n' + docs;
            const mojibakeCount = countMojibakeChars(fullText);
            const mojibakePercent = totalChars > 0 ? ((mojibakeCount / totalChars) * 100).toFixed(1) : 0;
            
            // Показываем сообщение о качестве текста в message-area
            showMojibakeMessage(mojibakePercent, mojibakeCount, totalChars);
            
            // Метрики без mojibake (он теперь отображается выше)
            ragMetrics.textContent = info;
        }, 250);
    }

    // Анализ (через бэкенд /ai_rag/analyze)
    async function startAnalysis() {
        const files = getSelectedFiles();
        const prompt = (ragPromptText.value || '').trim();
        if (!prompt) {
            return MessageManager.warning('Введите промпт', 'ragModal');
        }
        if (!files || files.length === 0) {
            return MessageManager.warning('Выберите файлы для анализа', 'ragModal');
        }

    // Сохраняем состояние модала; модал оставляем открытым, чтобы показывать прогресс
    const wasModalOpen = ragModal.style.display === 'block';
        
        // Запускаем таймер
        startAnalysisTimer();
        
        // Определяем max_output_tokens в зависимости от модели
        // Глубокий анализ всегда включён
        let maxTokens;
        
        // Для моделей o1-серии и deepseek-reasoner увеличиваем лимит, так как они генерируют длинные рассуждения
        if (selectedModelId && (selectedModelId.startsWith('o1') || selectedModelId === 'deepseek-reasoner')) {
            maxTokens = 16000;
        } else {
            maxTokens = 2500;
        }
        
        try {
            const usdRubRate = getUsdRubRate();
            
            // Собираем параметры для запроса
            const requestData = {
                file_paths: files,
                prompt,
                model_id: selectedModelId,
                top_k: 8,
                max_output_tokens: maxTokens,
                temperature: 0.3,
                usd_rub_rate: usdRubRate > 0 ? usdRubRate : null
            };
            
            // Проверяем, включен ли режим поиска для выбранной модели
            const model = models.find(m => m.model_id === selectedModelId);
            const isSearchMode = model && model.supports_search && model.search_enabled;
            
            if (isSearchMode) {
                // Передаем флаг, что используется режим поиска
                requestData.search_enabled = true;
                
                // Собираем параметры поиска
                const searchParams = {};
                
                // Количество результатов
                const maxResults = parseInt(searchMaxResults?.value) || 10;
                if (maxResults >= 1 && maxResults <= 20) {
                    searchParams.max_results = maxResults;
                }
                
                // Фильтр доменов
                const domainFilter = (searchDomainFilter?.value || '').trim();
                if (domainFilter) {
                    searchParams.search_domain_filter = domainFilter.split(',').map(d => d.trim()).filter(d => d);
                }
                
                // Свежесть
                const recency = (searchRecency?.value || '').trim();
                if (recency) {
                    searchParams.search_recency_filter = recency;
                }
                
                // Даты (конвертируем в MM/DD/YYYY)
                const afterDate = searchAfterDate?.value;
                if (afterDate) {
                    const d = new Date(afterDate);
                    searchParams.search_after_date = `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}`;
                }
                const beforeDate = searchBeforeDate?.value;
                if (beforeDate) {
                    const d = new Date(beforeDate);
                    searchParams.search_before_date = `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}`;
                }
                
                // Страна
                const country = (searchCountry?.value || '').trim().toUpperCase();
                if (country && country.length === 2) {
                    searchParams.country = country;
                }
                
                // Токены на страницу
                const maxTokensPerPage = parseInt(searchMaxTokens?.value) || 1024;
                if (maxTokensPerPage >= 256 && maxTokensPerPage <= 4096) {
                    searchParams.max_tokens_per_page = maxTokensPerPage;
                }
                
                // Добавляем параметры в запрос
                requestData.search_params = searchParams;

                // Если включён режим "Новый запрос" для выбранной модели — добавляем флаги
                if (model && model.new_request_enabled) {
                    requestData.force_web_search = true;
                    requestData.clear_document_context = true;
                }
                
                // Сохраняем параметры в модель для последующего использования
                await saveSearchApiParams(selectedModelId, searchParams);
            }
            
            const res = await fetch('/ai_rag/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
            
            // Проверяем Content-Type перед парсингом JSON
            const contentType = res.headers.get('content-type');
            let data;
            
            if (!contentType || !contentType.includes('application/json')) {
                // Сервер вернул не-JSON (например, текст ошибки)
                finishAnalysisTimer(false); // Показываем ошибку в прогресс-баре
                const text = await res.text();
                const errorMsg = `❌ Ошибка сервера (HTTP ${res.status}): ${text.substring(0, 300)}`;
                MessageManager.error(errorMsg, 'ragModal', 0); // 0 = не скрывать автоматически
                if (wasModalOpen) {
                    ragModal.style.display = 'block';
                }
                return;
            }
            
            try {
                data = await res.json();
            } catch (jsonErr) {
                finishAnalysisTimer(false); // Показываем ошибку в прогресс-баре
                const text = await res.text();
                const errorMsg = `❌ Ошибка парсинга JSON-ответа: ${jsonErr.message}. Ответ сервера: ${text.substring(0, 300)}`;
                MessageManager.error(errorMsg, 'ragModal', 0); // 0 = не скрывать автоматически
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
                finishAnalysisTimer(false); // Показываем ошибку в прогресс-баре
                const errorMsg = `❌ Ошибка AI-анализа: ${data.message || 'Неизвестная ошибка'}`;
                const errorDetails = data.error ? `\n\nДетали: ${data.error}` : '';
                MessageManager.error(errorMsg + errorDetails, 'ragModal', 0); // 0 = не скрывать автоматически
                if (wasModalOpen) {
                    ragModal.style.display = 'block';
                }
            }
        } catch (e) {
            // При ошибке сети возвращаем модал обратно
            finishAnalysisTimer(false); // Показываем ошибку в прогресс-баре
            const errorMsg = `❌ Ошибка сети или соединения: ${e.message}\n\nПроверьте подключение к интернету и доступность API.`;
            MessageManager.error(errorMsg, 'ragModal', 0); // 0 = не скрывать автоматически
            if (wasModalOpen) {
                ragModal.style.display = 'block';
            }
        }
    }

    // Привязка событий
    async function openRag() {
        const files = getSelectedFiles();
        if (!files || files.length === 0) {
            return MessageManager.warning('Выберите файлы для анализа (галочки слева от файлов)', 'main');
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
                    MessageManager.info(st.api_key_configured ? 'API-ключ настроен' : 'API-ключ не найден', 'ragModal');
                }
            } catch (_) {}
            await loadModels();
            loadUsdRubRate(); // Загружаем курс из localStorage
            renderModelsList();
            modelSelectModal.style.display = 'block';
        });
    }
    // обработчики открытия уже привязаны выше
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
                    MessageManager.warning('Выберите хотя бы одну модель', 'ragModal', 0);
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
                    await loadModels();
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
        aiResultClose.addEventListener('click', () => {
            aiResultModal.style.display = 'none';
            // Возвращаемся к модалу RAG
            if (ragModal) ragModal.style.display = 'block';
        });
    }
    
    const closeResultBtn = document.getElementById('closeResultBtn');
    const copyResultBtn = document.getElementById('copyResultBtn');
    const saveResultBtn = document.getElementById('saveResultBtn');
    const openNewTabBtn = document.getElementById('openNewTabBtn');
    const exportDocxBtn = document.getElementById('exportDocxBtn');
    
    if (closeResultBtn) {
        closeResultBtn.addEventListener('click', () => {
            aiResultModal.style.display = 'none';
            // Возвращаемся к модалу RAG
            if (ragModal) ragModal.style.display = 'block';
        });
    }
    
    if (copyResultBtn) {
        copyResultBtn.addEventListener('click', function() {
            // Получаем текст из сохраненного результата или из textarea
            let text = '';
            
            if (window._lastAnalysisResult && window._lastAnalysisResult.answer) {
                // Используем исходный Markdown текст
                const result = window._lastAnalysisResult;
                text = `Модель: ${result.model}\n`;
                
                // Стоимость в зависимости от модели тарификации
                if (result.cost?.pricing_model === 'per_request') {
                    text += `Стоимость: $${result.cost?.total || 0} (${result.cost?.requests_count || 1} запрос)\n`;
                } else {
                    text += `Стоимость: $${result.cost?.total || 0}\n`;
                }
                
                if (result.cost?.total_rub) {
                    text += `В рублях: ₽${result.cost.total_rub} (по курсу $${result.cost.usd_to_rub_rate})\n`;
                }
                
                if (result.usage?.total_tokens) {
                    text += `Токены: ${result.usage.total_tokens}\n`;
                }
                
                text += `\n${'='.repeat(80)}\n\n`;
                text += result.answer;
            } else {
                text = aiResultText.value;
            }
            
            if (!text) {
                MessageManager.warning('Нет текста для копирования', 'ragModal');
                return;
            }
            
            navigator.clipboard.writeText(text)
                .then(() => MessageManager.success('Результат скопирован в буфер обмена', 'ragModal'))
                .catch(error => MessageManager.error('Ошибка копирования: ' + error, 'ragModal'));
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
                
                // Стоимость в зависимости от модели тарификации
                if (result.cost?.pricing_model === 'per_request') {
                    text += `Стоимость: $${result.cost?.total || 0} (${result.cost?.requests_count || 1} запрос)\n`;
                } else {
                    text += `Стоимость: $${result.cost?.total || 0} (вход: $${result.cost?.input || 0}, выход: $${result.cost?.output || 0})\n`;
                }
                
                if (result.cost?.total_rub) {
                    if (result.cost?.pricing_model === 'per_request') {
                        text += `В рублях: ₽${result.cost.total_rub} по курсу $${result.cost.usd_to_rub_rate}\n`;
                    } else {
                        text += `В рублях: ₽${result.cost.total_rub} (вход: ₽${result.cost.input_rub}, выход: ₽${result.cost.output_rub}) по курсу $${result.cost.usd_to_rub_rate}\n`;
                    }
                }
                
                // Для Search API показываем количество запросов вместо токенов
                if (result.cost?.pricing_model === 'per_request') {
                    text += `Запросы: ${result.cost?.requests_count || 1}\n`;
                } else if (result.usage?.total_tokens) {
                    text += `Токены: ${result.usage.total_tokens} (вход: ${result.usage.input_tokens || 0}, выход: ${result.usage.output_tokens || 0})\n`;
                }
                
                text += `${'='.repeat(80)}\n\n`;
                text += result.answer;
            } else {
                text = aiResultText.value;
            }
            if (!text) {
                MessageManager.warning('Нет текста для сохранения', 'ragModal');
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
            MessageManager.success(`Результат сохранён: ${filename}`, 'ragModal');
        });
    }
    
    // Кнопка "Открыть в новой вкладке"
    if (openNewTabBtn) {
        openNewTabBtn.addEventListener('click', async function() {
            if (!window._lastAnalysisResult || !window._lastAnalysisResult.answer) {
                MessageManager.warning('Нет результата для отображения', 'ragModal');
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
                        MessageManager.success('Результат открыт в новой вкладке', 'ragModal');
                    } else {
                        MessageManager.warning('Не удалось открыть новое окно. Проверьте настройки браузера.', 'ragModal');
                    }
                } else {
                    MessageManager.error(data.message || 'Ошибка получения HTML', 'ragModal');
                }
            } catch (err) {
                MessageManager.error('Ошибка открытия в новой вкладке: ' + err.message, 'ragModal');
            }
        });
    }
    
    // Кнопка "Сохранить как DOCX"
    if (exportDocxBtn) {
        exportDocxBtn.addEventListener('click', async function() {
            if (!window._lastAnalysisResult || !window._lastAnalysisResult.answer) {
                MessageManager.warning('Нет результата для экспорта', 'ragModal');
                return;
            }
            
            try {
                MessageManager.info('Создание DOCX файла...', 'ragModal', 0);
                
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
                    
                    MessageManager.success(`DOCX файл сохранён: ${filename}`, 'ragModal');
                } else {
                    const errorText = await res.text();
                    MessageManager.error('Ошибка экспорта: ' + errorText.substring(0, 100), 'ragModal');
                }
            } catch (err) {
                MessageManager.error('Ошибка экспорта DOCX: ' + err.message, 'ragModal');
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
        
        // Обработчик slider для токенов Search API
        if (searchMaxTokens && searchMaxTokensValue) {
            searchMaxTokens.addEventListener('input', (e) => {
                searchMaxTokensValue.textContent = e.target.value;
            });
        }

        // Сохранить/Загрузить промпт в RAG
        if (ragSavePromptBtn) {
            ragSavePromptBtn.addEventListener('click', async () => {
                const prompt = (ragPromptText.value || '').trim();
                if (!prompt) return MessageManager.warning('Промпт пуст', 'ragModal');
                
                // Загружаем список существующих промптов
                try {
                    const res = await fetch('/ai_analysis/prompts/list');
                    const data = await res.json();
                    
                    if (!promptList || !promptListModal) return;
                    promptList.innerHTML = '';
                    
                    // Добавляем заголовок и поле для ввода нового имени
                    const header = document.createElement('div');
                    header.style.cssText = 'padding:15px; background:#2196f3; color:white; font-weight:600; font-size:16px;';
                    header.textContent = 'Сохранить промпт';
                    promptList.appendChild(header);
                    
                    const newNameBlock = document.createElement('div');
                    newNameBlock.style.cssText = 'padding:15px; background:#f0f0f0; border-bottom:2px solid #ddd;';
                    const newNameLabel = document.createElement('div');
                    newNameLabel.style.cssText = 'font-weight:600; margin-bottom:8px;';
                    newNameLabel.textContent = '💾 Создать новый промпт:';
                    const newNameInput = document.createElement('input');
                    newNameInput.type = 'text';
                    newNameInput.placeholder = 'Введите имя файла (без расширения)';
                    newNameInput.style.cssText = 'width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; font-size:14px;';
                    const saveNewBtn = document.createElement('button');
                    saveNewBtn.textContent = 'Сохранить как новый';
                    saveNewBtn.style.cssText = 'margin-top:10px; padding:8px 16px; background:#4caf50; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:600;';
                    saveNewBtn.onclick = async () => {
                        const filename = newNameInput.value.trim();
                        if (!filename) return MessageManager.warning('Введите имя файла', 'ragModal');
                        try {
                            const saveRes = await fetch('/ai_analysis/prompts/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ prompt, filename }) });
                            const saveData = await saveRes.json();
                            MessageManager.show(saveData.message || (saveData.success ? 'Промпт сохранён' : 'Не удалось сохранить промпт'), saveData.success ? 'success' : 'error', 'ragModal');
                            if (saveData.success) promptListModal.style.display = 'none';
                        } catch (e) { MessageManager.error('Ошибка сохранения: ' + e.message, 'ragModal'); }
                    };
                    newNameBlock.appendChild(newNameLabel);
                    newNameBlock.appendChild(newNameInput);
                    newNameBlock.appendChild(saveNewBtn);
                    promptList.appendChild(newNameBlock);
                    
                    // Если есть существующие промпты, показываем их
                    if (data.success && Array.isArray(data.prompts) && data.prompts.length > 0) {
                        const existingHeader = document.createElement('div');
                        existingHeader.style.cssText = 'padding:12px 15px; background:#e3f2fd; font-weight:600; border-bottom:1px solid #ddd;';
                        existingHeader.textContent = '📝 Или перезаписать существующий:';
                        promptList.appendChild(existingHeader);
                        
                        // Для каждого файла показываем превью и кнопку перезаписи
                        for (const filename of data.prompts) {
                            let preview = '';
                            try {
                                const r = await fetch('/ai_analysis/prompts/load/' + encodeURIComponent(filename));
                                const ld = await r.json();
                                if (ld.success && typeof ld.prompt === 'string') {
                                    const para = ld.prompt.split(/\n\s*\n/)[0] || ld.prompt;
                                    preview = para.trim().slice(0, 150);
                                }
                            } catch (_) {}
                            
                            const item = document.createElement('div');
                            item.style.cssText = 'padding:12px; margin:6px 0; background:#fff; border:1px solid #ddd; border-radius:6px; display:flex; justify-content:space-between; align-items:center;';
                            
                            const textBlock = document.createElement('div');
                            textBlock.style.cssText = 'flex:1;';
                            const title = document.createElement('div');
                            title.style.cssText = 'font-weight:600; margin-bottom:4px;';
                            title.textContent = filename;
                            const desc = document.createElement('div');
                            desc.style.cssText = 'font-size:12px; color:#666; white-space:pre-wrap;';
                            desc.textContent = preview || '(пусто)';
                            textBlock.appendChild(title);
                            textBlock.appendChild(desc);
                            
                            const overwriteBtn = document.createElement('button');
                            overwriteBtn.textContent = '♻️ Перезаписать';
                            overwriteBtn.style.cssText = 'padding:6px 12px; background:#ff9800; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:600; white-space:nowrap;';
                            overwriteBtn.onclick = async () => {
                                if (!confirm(`Перезаписать промпт "${filename}"?`)) return;
                                try {
                                    const saveRes = await fetch('/ai_analysis/prompts/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ prompt, filename }) });
                                    const saveData = await saveRes.json();
                                    MessageManager.show(saveData.message || (saveData.success ? 'Промпт перезаписан' : 'Не удалось перезаписать промпт'), saveData.success ? 'success' : 'error', 'ragModal');
                                    if (saveData.success) promptListModal.style.display = 'none';
                                } catch (e) { MessageManager.error('Ошибка перезаписи: ' + e.message, 'ragModal'); }
                            };
                            
                            item.appendChild(textBlock);
                            item.appendChild(overwriteBtn);
                            promptList.appendChild(item);
                        }
                    }
                    
                    // Показываем модальное окно
                    promptListModal.style.display = 'block';
                    newNameInput.focus();
                    
                } catch (e) { 
                    MessageManager.error('Ошибка загрузки списка промптов: ' + e.message, 'ragModal'); 
                }
            });
        }
        if (ragLoadPromptBtn) {
            ragLoadPromptBtn.addEventListener('click', async () => {
                try {
                    const res = await fetch('/ai_analysis/prompts/list');
                    const data = await res.json();
                    if (!data.success || !Array.isArray(data.prompts) || data.prompts.length === 0) {
                        return MessageManager.info('Нет сохранённых промптов', 'ragModal');
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
                                    MessageManager.error(ld.message || 'Не удалось загрузить промпт', 'ragModal');
                                }
                            } catch (e) { MessageManager.error('Ошибка загрузки: ' + e.message, 'ragModal'); }
                        });
                        promptList.appendChild(item);
                    }
                    promptListModal.style.display = 'block';
                } catch (e) { MessageManager.error('Ошибка загрузки списка промптов: ' + e.message, 'ragModal'); }
            });
        }

        // Закрытие модалки списка промптов
        if (promptListClose) promptListClose.addEventListener('click', () => promptListModal.style.display = 'none');
        if (closePromptListBtn) closePromptListBtn.addEventListener('click', () => promptListModal.style.display = 'none');

    // Экспортируем функции глобально для использования в text-optimizer.js
    window.updateRagMetrics = updateRagMetrics;
    
    // Инициализация при загрузке
    loadModels().then(() => {
        renderModelsList();
        toggleSearchApiParams();
        updateRagMetrics();
    });

})();
