// RAG Analysis Module
(function() {
    'use strict';

    // DOM элементы
    const ragAnalysisBtn = document.getElementById('ragAnalysisBtn');
    const ragIndexBtn = document.getElementById('ragIndexBtn');
    const ragStatusBtn = document.getElementById('ragStatusBtn');
    const ragStatus = document.getElementById('ragStatus');
    
    // Модальное окно промпта
    const ragPromptModal = document.getElementById('ragPromptModal');
    const ragPromptClose = document.getElementById('ragPromptClose');
    const ragPromptText = document.getElementById('ragPromptText');
    const ragTopK = document.getElementById('ragTopK');
    const ragMaxTokens = document.getElementById('ragMaxTokens');
    const ragSelectedCount = document.getElementById('ragSelectedCount');
    const ragEstimate = document.getElementById('ragEstimate');
    const ragEstInputTokens = document.getElementById('ragEstInputTokens');
    const ragEstOutputTokens = document.getElementById('ragEstOutputTokens');
    const ragEstTotalTokens = document.getElementById('ragEstTotalTokens');
    const ragEstCost = document.getElementById('ragEstCost');
    const ragEstimateBtn = document.getElementById('ragEstimateBtn');
    const ragStartAnalysisBtn = document.getElementById('ragStartAnalysisBtn');
    const ragCancelBtn = document.getElementById('ragCancelBtn');
    const ragSelectModelBtn = document.getElementById('ragSelectModelBtn');
    
    // Модальное окно модели
    const ragModelModal = document.getElementById('ragModelModal');
    const ragModelClose = document.getElementById('ragModelClose');
    const ragModelsList = document.getElementById('ragModelsList');
    const ragPriceInput = document.getElementById('ragPriceInput');
    const ragPriceOutput = document.getElementById('ragPriceOutput');
    const ragSavePricesBtn = document.getElementById('ragSavePricesBtn');
    const ragCloseModelBtn = document.getElementById('ragCloseModelBtn');
    
    // Модальное окно результатов
    const ragResultModal = document.getElementById('ragResultModal');
    const ragResultClose = document.getElementById('ragResultClose');
    const ragResultContent = document.getElementById('ragResultContent');
    const ragActualUsage = document.getElementById('ragActualUsage');
    const ragActualInputTokens = document.getElementById('ragActualInputTokens');
    const ragActualOutputTokens = document.getElementById('ragActualOutputTokens');
    const ragActualTotalTokens = document.getElementById('ragActualTotalTokens');
    const ragActualCost = document.getElementById('ragActualCost');
    const ragCopyResultBtn = document.getElementById('ragCopyResultBtn');
    const ragCloseResultBtn = document.getElementById('ragCloseResultBtn');

    // Состояние
    let currentModel = 'gpt-4o-mini';
    let models = [];

    // Инициализация
    document.addEventListener('DOMContentLoaded', function() {
        loadModels();
        checkStatus();
    });

    // Кнопка анализа
    if (ragAnalysisBtn) {
        ragAnalysisBtn.addEventListener('click', function() {
            const selectedFiles = getSelectedFiles();
            
            if (selectedFiles.length === 0) {
                showMessage('Выберите файлы для анализа (установите галочки)', 'error');
                return;
            }
            
            ragSelectedCount.textContent = selectedFiles.length;
            ragPromptModal.style.display = 'block';
        });
    }

    // Кнопка индексации
    if (ragIndexBtn) {
        ragIndexBtn.addEventListener('click', function() {
            const selectedFiles = getSelectedFiles();
            
            if (selectedFiles.length === 0) {
                showMessage('Выберите файлы для индексации (установите галочки)', 'error');
                return;
            }
            
            indexDocuments(selectedFiles);
        });
    }

    // Кнопка статуса
    if (ragStatusBtn) {
        ragStatusBtn.addEventListener('click', function() {
            checkStatus(true);
        });
    }

    // Закрытие модальных окон
    if (ragPromptClose) {
        ragPromptClose.addEventListener('click', () => ragPromptModal.style.display = 'none');
    }
    
    if (ragCancelBtn) {
        ragCancelBtn.addEventListener('click', () => ragPromptModal.style.display = 'none');
    }

    if (ragModelClose) {
        ragModelClose.addEventListener('click', () => ragModelModal.style.display = 'none');
    }
    
    if (ragCloseModelBtn) {
        ragCloseModelBtn.addEventListener('click', () => ragModelModal.style.display = 'none');
    }

    if (ragResultClose) {
        ragResultClose.addEventListener('click', () => ragResultModal.style.display = 'none');
    }
    
    if (ragCloseResultBtn) {
        ragCloseResultBtn.addEventListener('click', () => ragResultModal.style.display = 'none');
    }

    // Кнопка выбора модели
    if (ragSelectModelBtn) {
        ragSelectModelBtn.addEventListener('click', function() {
            ragModelModal.style.display = 'block';
            renderModels();
        });
    }

    // Кнопка оценки
    if (ragEstimateBtn) {
        ragEstimateBtn.addEventListener('click', function() {
            estimateRequest();
        });
    }

    // Кнопка анализа
    if (ragStartAnalysisBtn) {
        ragStartAnalysisBtn.addEventListener('click', function() {
            startAnalysis();
        });
    }

    // Сохранение цен
    if (ragSavePricesBtn) {
        ragSavePricesBtn.addEventListener('click', function() {
            savePrices();
        });
    }

    // Копирование результатов
    if (ragCopyResultBtn) {
        ragCopyResultBtn.addEventListener('click', function() {
            copyResults();
        });
    }

    // Используем глобальную функцию getSelectedFiles из script.js
    function getSelectedFiles() {
        return window.getSelectedFiles ? window.getSelectedFiles() : [];
    }

    // Загрузить модели
    function loadModels() {
        fetch('/ai_rag/models')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    models = data.models || [];
                    currentModel = data.default_model || 'gpt-4o-mini';
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки моделей:', error);
            });
    }

    // Отрисовать список моделей
    function renderModels() {
        if (models.length === 0) {
            ragModelsList.innerHTML = '<p>Модели не загружены</p>';
            return;
        }

        let html = '<div style="display: flex; flex-direction: column; gap: 10px;">';
        
        models.forEach(model => {
            const isSelected = model.model_id === currentModel;
            const bgColor = isSelected ? '#e3f2fd' : '#fff';
            
            html += `
                <div style="padding: 10px; background: ${bgColor}; border: 1px solid #ddd; border-radius: 4px; cursor: pointer;" 
                     onclick="window.ragSelectModel('${model.model_id}')">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>${model.display_name}</strong>
                            <div style="font-size: 12px; color: #666;">
                                Контекст: ${model.context_window_tokens.toLocaleString()} токенов
                            </div>
                        </div>
                        <div style="text-align: right; font-size: 12px;">
                            <div>Вход: ${model.price_input_per_1m || 0}</div>
                            <div>Выход: ${model.price_output_per_1m || 0}</div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        ragModelsList.innerHTML = html;
        
        // Обновляем поля цен для текущей модели
        const model = models.find(m => m.model_id === currentModel);
        if (model) {
            ragPriceInput.value = model.price_input_per_1m || 0;
            ragPriceOutput.value = model.price_output_per_1m || 0;
        }
    }

    // Выбрать модель
    window.ragSelectModel = function(modelId) {
        currentModel = modelId;
        renderModels();
    };

    // Сохранить цены
    function savePrices() {
        const priceInput = parseFloat(ragPriceInput.value) || 0;
        const priceOutput = parseFloat(ragPriceOutput.value) || 0;

        fetch('/ai_rag/models', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model_id: currentModel,
                price_input_per_1m: priceInput,
                price_output_per_1m: priceOutput
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showMessage('Цены сохранены', 'success');
                loadModels();
            } else {
                showMessage(data.message || 'Ошибка сохранения', 'error');
            }
        })
        .catch(error => {
            showMessage('Ошибка сети: ' + error.message, 'error');
        });
    }

    // Оценить запрос
    function estimateRequest() {
        const selectedFiles = getSelectedFiles();
        const prompt = ragPromptText.value.trim();
        const topK = parseInt(ragTopK.value) || 5;
        const maxTokens = parseInt(ragMaxTokens.value) || 600;

        if (!prompt) {
            showMessage('Введите промпт', 'error');
            return;
        }

        fetch('/ai_rag/estimate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_paths: selectedFiles,
                prompt: prompt,
                model_id: currentModel,
                top_k: topK,
                expected_output_tokens: maxTokens
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                ragEstInputTokens.textContent = data.input_tokens.toLocaleString();
                ragEstOutputTokens.textContent = data.output_tokens.toLocaleString();
                ragEstTotalTokens.textContent = data.total_tokens.toLocaleString();
                ragEstCost.textContent = data.total_cost.toFixed(4);
                ragEstimate.style.display = 'block';
            } else {
                showMessage(data.message || 'Ошибка оценки', 'error');
            }
        })
        .catch(error => {
            showMessage('Ошибка сети: ' + error.message, 'error');
        });
    }

    // Начать анализ
    function startAnalysis() {
        const selectedFiles = getSelectedFiles();
        const prompt = ragPromptText.value.trim();
        const topK = parseInt(ragTopK.value) || 5;
        const maxTokens = parseInt(ragMaxTokens.value) || 600;

        if (!prompt) {
            showMessage('Введите промпт', 'error');
            return;
        }

        ragPromptModal.style.display = 'none';
        showMessage('Выполняется RAG-анализ...', 'info');

        fetch('/ai_rag/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_paths: selectedFiles,
                prompt: prompt,
                model_id: currentModel,
                top_k: topK,
                max_output_tokens: maxTokens,
                temperature: 0.3
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showResults(data.result);
                showMessage('Анализ выполнен успешно', 'success');
            } else {
                showMessage(data.message || 'Ошибка анализа', 'error');
            }
        })
        .catch(error => {
            showMessage('Ошибка сети: ' + error.message, 'error');
        });
    }

    // Показать результаты
    function showResults(result) {
        let html = '';

        // Summary
        if (result.summary && result.summary.length > 0) {
            html += '<div style="margin-bottom: 20px;"><h3>Краткая выжимка:</h3><ul>';
            result.summary.forEach(item => {
                html += `<li>${escapeHtml(item)}</li>`;
            });
            html += '</ul></div>';
        }

        // Equipment
        if (result.equipment && result.equipment.length > 0) {
            html += '<div style="margin-bottom: 20px;"><h3>Оборудование:</h3>';
            result.equipment.forEach((eq, idx) => {
                html += '<div style="padding: 10px; background: #f9f9f9; margin: 10px 0; border-radius: 4px;">';
                html += `<strong>${idx + 1}. ${escapeHtml(eq.name || 'Без названия')}</strong>`;
                
                if (eq.model) {
                    html += ` <span style="color: #666;">(${escapeHtml(eq.model)})</span>`;
                }
                
                if (eq.characteristics) {
                    html += '<div style="margin-top: 5px;"><em>Характеристики:</em><ul style="margin: 5px 0;">';
                    for (const [key, value] of Object.entries(eq.characteristics)) {
                        html += `<li>${escapeHtml(key)}: ${escapeHtml(value)}</li>`;
                    }
                    html += '</ul></div>';
                }
                
                if (eq.qty) {
                    html += `<div>Количество: ${eq.qty} ${eq.unit || 'шт'}</div>`;
                }
                
                html += '</div>';
            });
            html += '</div>';
        }

        // Installation
        if (result.installation) {
            html += '<div style="margin-bottom: 20px;"><h3>Монтаж:</h3>';
            const verdict = result.installation.verdict;
            const verdictText = verdict === true ? 'Требуется' : verdict === false ? 'Не требуется' : 'Неизвестно';
            const verdictColor = verdict === true ? '#4caf50' : verdict === false ? '#f44336' : '#ff9800';
            
            html += `<div style="padding: 10px; background: ${verdictColor}22; border-left: 4px solid ${verdictColor}; margin: 10px 0;">`;
            html += `<strong>Вердикт:</strong> ${verdictText}`;
            html += '</div>';
            
            if (result.installation.evidence && result.installation.evidence.length > 0) {
                html += '<div><em>Подтверждения:</em><ul>';
                result.installation.evidence.forEach(ev => {
                    html += `<li style="font-size: 14px; color: #555;">${escapeHtml(ev)}</li>`;
                });
                html += '</ul></div>';
            }
            html += '</div>';
        }

        ragResultContent.innerHTML = html;

        // Показываем использование токенов
        if (result.usage) {
            ragActualInputTokens.textContent = result.usage.input_tokens.toLocaleString();
            ragActualOutputTokens.textContent = result.usage.output_tokens.toLocaleString();
            ragActualTotalTokens.textContent = result.usage.total_tokens.toLocaleString();
            
            if (result.cost) {
                ragActualCost.textContent = result.cost.total.toFixed(4);
            } else {
                ragActualCost.textContent = '0.0000';
            }
            
            ragActualUsage.style.display = 'block';
        }

        ragResultModal.style.display = 'block';
    }

    // Индексировать документы
    function indexDocuments(filePaths) {
        showMessage('Индексация документов...', 'info');

        fetch('/ai_rag/index', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_paths: filePaths
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const msg = `Проиндексировано ${data.total_chunks} чанков из ${filePaths.length} файлов`;
                showMessage(msg, 'success');
            } else {
                showMessage(data.message || 'Ошибка индексации', 'error');
            }
        })
        .catch(error => {
            showMessage('Ошибка сети: ' + error.message, 'error');
        });
    }

    // Проверить статус
    function checkStatus(showAlert = false) {
        fetch('/ai_rag/status')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const db = data.database_available ? '✓ БД' : '✗ БД';
                    const api = data.api_key_configured ? '✓ API' : '✗ API';
                    let stats = '';
                    
                    if (data.database_stats) {
                        stats = ` (Документов: ${data.database_stats.documents}, Чанков: ${data.database_stats.chunks})`;
                    }
                    
                    ragStatus.textContent = `Статус: ${db} ${api}${stats}`;
                    
                    if (showAlert) {
                        const msg = `RAG статус:\n- База данных: ${data.database_available ? 'доступна' : 'недоступна'}\n- API ключ: ${data.api_key_configured ? 'настроен' : 'не настроен'}${stats}`;
                        alert(msg);
                    }
                } else {
                    ragStatus.textContent = 'Статус: недоступен';
                }
            })
            .catch(error => {
                console.error('Ошибка проверки статуса:', error);
                ragStatus.textContent = 'Статус: ошибка';
            });
    }

    // Копировать результаты
    function copyResults() {
        const text = ragResultContent.innerText;
        navigator.clipboard.writeText(text).then(() => {
            showMessage('Результаты скопированы', 'success');
        }).catch(() => {
            showMessage('Ошибка копирования', 'error');
        });
    }

    // Вспомогательные функции
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
