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

    // Получить список выбранных файлов
    function getSelectedFiles() {
        const checkboxes = document.querySelectorAll('.file-checkbox:checked');
        const files = [];
        checkboxes.forEach(cb => {
            files.push(cb.getAttribute('data-file-path'));
        });
        return files;
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
        optimizeTextBtn.addEventListener('click', function() {
            if (!currentText) {
                showMessage('Сначала нужно начать анализ, чтобы получить текст для оптимизации', 'info');
                return;
            }
            
            const promptLength = aiPromptText.value.length;
            const targetSize = maxRequestSize - promptLength - 100; // Запас
            
            fetch('/ai_analysis/optimize_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: currentText,
                    target_size: targetSize
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentText = data.optimized_text;
                    showMessage(`Текст оптимизирован: ${data.original_size} → ${data.optimized_size} символов (сокращено на ${data.reduction})`, 'success');
                } else {
                    showMessage(data.message, 'error');
                }
            })
            .catch(error => {
                showMessage('Ошибка оптимизации: ' + error, 'error');
            });
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

    // Показать сообщение (использует существующую функцию из script.js)
    function showMessage(message, type) {
        // Если есть глобальная функция showModal из script.js
        if (typeof window.showModal === 'function') {
            window.showModal(message);
        } else {
            // Fallback: используем alert
            alert(message);
        }
    }

})();
