// --- Drag & Drop ---
const selectFolderBtn = document.getElementById('selectFolderBtn');
const selectFilesBtn = document.getElementById('selectFilesBtn');
const selectedFolderPathEl = document.getElementById('selectedFolderPath');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const filesList = document.getElementById('filesList');
const fileCount = document.getElementById('fileCount');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const deleteFilesBtn = document.getElementById('deleteFilesBtn');
const messageModal = document.getElementById('messageModal');
const modalMessage = document.getElementById('modalMessage');
const closeModal = document.querySelector('.close');
const indexStatus = document.getElementById('indexStatus');

// --- Folder Select (experimental, works in Chromium browsers) ---
selectFolderBtn.addEventListener('click', () => {
    const folderInput = document.createElement('input');
    folderInput.type = 'file';
    folderInput.webkitdirectory = true;
    folderInput.multiple = true;
    folderInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt,.html,.htm,.csv,.tsv,.xml,.json';
    folderInput.style.display = 'none';
    folderInput.addEventListener('change', handleFiles);
    document.body.appendChild(folderInput);
    folderInput.click();
    folderInput.remove();
});

// --- File Select ---
selectFilesBtn.addEventListener('click', () => {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.multiple = true;
    fileInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt,.html,.htm,.csv,.tsv,.xml,.json';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', handleFiles);
    document.body.appendChild(fileInput);
    fileInput.click();
    fileInput.remove();
});

// --- Upload Files ---
function handleFiles(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    // Отобразим полный путь выбранной папки по первому файлу
    try {
        const any = files[0];
        const wrp = any && any.webkitRelativePath ? any.webkitRelativePath : '';
        if (wrp) {
            const parts = wrp.split('/');
            const folderPath = parts.slice(0, -1).join('/');
            // Попытаемся получить полный путь из webkitdirectory API
            if (any.webkitdirectory && any.path) {
                // Если доступен полный путь - используем его
                const fullPath = any.path.replace('/' + any.name, '').replace(folderPath, '');
                if (selectedFolderPathEl) selectedFolderPathEl.textContent = fullPath + '/' + folderPath;
            } else {
                // Иначе показываем относительный путь как есть
                if (selectedFolderPathEl) selectedFolderPathEl.textContent = folderPath;
            }
        }
    } catch (_) {}
    uploadProgress.style.display = 'flex';
    let uploaded = 0;
    progressFill.style.width = '0%';
    progressText.textContent = '0%';

    const formData = new FormData();
    const allowedExt = new Set(['pdf','doc','docx','xls','xlsx','txt','html','htm','csv','tsv','xml','json']);
    let skipped = 0;
    for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const baseName = (f.webkitRelativePath || f.name || '').split('/').pop();
        if (!baseName) { continue; }
        // Пропускаем временные файлы Office (~$, $)
        if (baseName.startsWith('~$') || baseName.startsWith('$')) {
            skipped++;
            continue;
        }
        // Пропускаем неподдерживаемые расширения
        const dot = baseName.lastIndexOf('.');
        const ext = dot >= 0 ? baseName.slice(dot + 1).toLowerCase() : '';
        if (!allowedExt.has(ext)) {
            skipped++;
            continue;
        }
        // Сохраняем относительный путь внутри архива папки
        const relName = f.webkitRelativePath || f.name;
        formData.append('files', f, relName);
    }

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => {
        if (res.status === 413) {
            return res.json().then(j => { throw new Error(j.error || 'Файл слишком большой'); });
        }
        return res.json();
    })
    .then(data => {
        if (data.success) {
            // 1) Сразу обновляем дерево файлов, чтобы пользователь видел структуру
            try { updateFilesList(); } catch (_) {}
            // 2) Запускаем построение индекса в фоне (без ожидания), чтобы не блокировать UI
            try { rebuildIndexWithProgress().catch(() => {}); } catch (_) {}
        } else {
            throw new Error(data.error || 'Ошибка загрузки папки');
        }
    })
    .then(() => { uploadProgress.style.display = 'none'; })
    .catch((err) => {
        showMessage(err && err.message ? err.message : 'Ошибка загрузки файлов');
        uploadProgress.style.display = 'none';
    });
}

// --- Update Files List ---
function updateFilesList() {
    return fetch('/files_json')
        .then(res => res.json())
        .then(data => {
            const { folders = {}, file_statuses = {} } = data;
            
            // Сохраняем состояния открытых/закрытых папок
            const folderStates = {};
            document.querySelectorAll('.folder-container').forEach(container => {
                const id = container.id;
                const content = container.querySelector('.folder-content');
                if (content) {
                    folderStates[id] = content.style.display !== 'none';
                }
            });
            
            // Очищаем список
            filesList.innerHTML = '';
            
            // Отображаем папки
            Object.keys(folders).sort().forEach(folderKey => {
                const files = folders[folderKey];
                const folderName = folderKey === 'root' ? 'Загруженные файлы' : folderKey;
                const folderId = `folder-${folderName}`;
                const isExpanded = folderStates[folderId] !== false; // По умолчанию развёрнуты
                
                const folderDiv = document.createElement('div');
                folderDiv.className = 'folder-container';
                folderDiv.id = folderId;
                
                const headerDiv = document.createElement('div');
                headerDiv.className = 'folder-header';
                headerDiv.onclick = () => toggleFolder(folderName);
                
                headerDiv.innerHTML = `
                    <span class="folder-icon">📁</span>
                    <span class="folder-name">${escapeHtml(folderName)}</span>
                    <span class="file-count-badge">${files.length}</span>
                    <span class="toggle-icon">${isExpanded ? '▼' : '▶'}</span>
                `;
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'folder-content';
                contentDiv.style.display = isExpanded ? 'block' : 'none';
                
                // Добавляем файлы
                files.forEach(file => {
                    const fileDiv = renderFileItem(file, file_statuses);
                    contentDiv.appendChild(fileDiv);
                });
                
                folderDiv.appendChild(headerDiv);
                folderDiv.appendChild(contentDiv);
                filesList.appendChild(folderDiv);
            });
            
            // Обновляем количество файлов
            if (fileCount) {
                fileCount.textContent = data.total_files || 0;
            }
            
            // Обновляем статус индекса
            refreshIndexStatus();
            
            // Применяем термины поиска к ссылкам
            applyQueryToViewLinks();
            return true;
        })
        .catch(err => {
            console.error('Ошибка загрузки списка файлов:', err);
            // Fallback: используем старый метод
            return fetch('/')
                .then(res => res.text())
                .then(html => {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    const newFilesList = doc.getElementById('filesList');
                    if (newFilesList && filesList) {
                        filesList.innerHTML = newFilesList.innerHTML;
                        setTimeout(restoreFolderStates, 100);
                    }
                    return true;
                });
        });
}

function renderFileItem(file, file_statuses) {
    // Simplified file item rendering without archives and traffic lights
    const wrapper = document.createElement('div');
    wrapper.className = 'file-item-wrapper';
    wrapper.dataset.filePath = file.path;
    
    const fileDiv = document.createElement('div');
    
    // Получаем статус файла
    const fileStatus = file_statuses[file.path] || {};
    const status = fileStatus.status || 'not_checked';
    const charCount = fileStatus.char_count;
    const isUnreadable = (status === 'unsupported') || (status === 'error') || (charCount === 0);
    
    fileDiv.className = 'file-item' + (isUnreadable ? ' file-disabled' : '');
    
    // Формируем HTML файла
    const sizeKB = (file.size / 1024).toFixed(1);
    let fileLink;
    
    if (isUnreadable) {
        fileLink = `<span class="file-name" title="Файл недоступен для просмотра/скачивания">${escapeHtml(file.name)}</span>`;
    } else {
        fileLink = `<a class="file-name result-file-link" href="/view/${encodeURIComponent(file.path)}" target="_blank" rel="noopener">${escapeHtml(file.name)}</a>`;
    }
    
    let charCountHtml = '';
    if (charCount !== null && charCount !== undefined) {
        charCountHtml = `<span class="file-chars${charCount === 0 ? ' text-danger' : ''}">Символов: ${charCount}</span>`;
    }
    
    let errorHtml = '';
    if (fileStatus.error) {
        errorHtml = `<span class="file-error text-danger">${escapeHtml(fileStatus.error)}</span>`;
    } else if (status === 'unsupported') {
        errorHtml = `<span class="file-error text-danger">Неподдерживаемый формат</span>`;
    }
    
    fileDiv.innerHTML = `
        <div class="file-info">
            <span class="file-icon">📄</span>
            <div class="file-details">
                ${fileLink}
                <span class="file-size">${sizeKB} KB</span>
                ${charCountHtml}
                ${errorHtml}
            </div>
        </div>
    `;
    
    wrapper.appendChild(fileDiv);
    
    // Контейнер для результатов поиска
    const resultsContainer = document.createElement('div');
    resultsContainer.className = 'file-search-results';
    resultsContainer.style.display = 'none';
    wrapper.appendChild(resultsContainer);
    
    return wrapper;
}

// --- Search ---

async function performSearch(terms) {
    // Очищаем все предыдущие результаты под файлами
    document.querySelectorAll('.file-search-results').forEach(el => {
        el.style.display = 'none';
        el.innerHTML = '';
    });
    document.querySelectorAll('.file-item-wrapper[data-has-results]')
        .forEach(w => w.removeAttribute('data-has-results'));
    
    // Устанавливаем глобальный флаг, что поиск был выполнен
    window.searchWasPerformed = true;
    
    const resp = await fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            search_terms: terms
        })
    });
    const data = await resp.json();
    try { localStorage.setItem('last_search_terms', terms); } catch (e) {}
    // Критично: сначала обновляем список файлов и дожидаемся рендера, чтобы не потерять результаты
    await updateFilesList();
    
    if (data.results && data.results.length > 0) {
        const t = termsFromInput();
        
        // Группируем результаты по файлам и отображаем под каждым файлом
        const resultsByFile = {};
        data.results.forEach(result => {
            const filePath = result.source || result.path;
            if (!resultsByFile[filePath]) {
                resultsByFile[filePath] = {
                    filename: result.filename,
                    perTerm: []
                };
            }
            if (result.per_term) {
                resultsByFile[filePath].perTerm.push(...result.per_term);
            }
        });
        
        // Отображаем результаты под соответствующими файлами
        Object.keys(resultsByFile).forEach(filePath => {
            const fileWrapper = document.querySelector(`.file-item-wrapper[data-file-path="${CSS.escape(filePath)}"]`);
            if (fileWrapper) {
                const resultsContainer = fileWrapper.querySelector('.file-search-results');
                if (resultsContainer) {
                    // До 2 сниппетов на термин
                    const maxSnippets = 2;
                    
                    const perTermHtml = resultsByFile[filePath].perTerm.map(entry => {
                        const snips = (entry.snippets || []).slice(0, maxSnippets).map(s => 
                            `<div class="context-snippet">${escapeHtml(s)}</div>`
                        ).join('');
                        
                        const termHtml = `${escapeHtml(entry.term)} (${entry.count})`;
                        
                        return `<div class="per-term-block">
                            <div class="found-terms"><span class="found-term">${termHtml}</span></div>
                            <div class="context-snippets">${snips || '<div class="context-empty">Нет сниппетов</div>'}</div>
                        </div>`;
                    }).join('');
                    
                    resultsContainer.innerHTML = perTermHtml;
                    resultsContainer.style.display = 'block';
                    fileWrapper.setAttribute('data-has-results', '1');
                }
            }
        });
        
        // Раскрываем папки с результатами, если они не были вручную свернуты
        expandFoldersWithResults();

        highlightSnippets(t);
        applyQueryToViewLinks();
    } else {
        // Нет результатов
    }
}

function refreshSearchResultsIfActive() {
    const terms = searchInput.value.trim();
    
    if (!terms) {
        // FR-003: если запрос пуст — скрываем все результаты под файлами
        document.querySelectorAll('.file-search-results').forEach(el => {
            el.style.display = 'none';
            el.innerHTML = '';
        });
        return;
    }
    // Если есть термины - перезапускаем поиск
    performSearch(terms);
}

// Функция для раскрытия папок с результатами (учитывает ручное состояние)
function expandFoldersWithResults() {
    // Собираем папки, которые содержат результаты поиска
    const foldersWithResults = new Set();
    
    // Проверяем обычные папки
    document.querySelectorAll('.folder-container:not(.archive-folder)').forEach(folderContainer => {
        const hasResults = folderContainer.querySelector('.file-search-results[style*="display: block"]');
        if (hasResults) {
            const folderName = folderContainer.querySelector('.folder-name')?.textContent;
            if (folderName) {
                // Проверяем, не была ли папка вручную свернута
                const savedState = localStorage.getItem('folder-' + folderName);
                if (savedState !== 'collapsed') {
                    folderContainer.classList.remove('collapsed');
                    const contentDiv = folderContainer.querySelector('.folder-content');
                    const toggleIcon = folderContainer.querySelector('.toggle-icon');
                    if (contentDiv) contentDiv.style.display = 'block';
                    if (toggleIcon) toggleIcon.textContent = '▼';
                }
            }
        }
    });
    
    // Проверяем архивные папки
    document.querySelectorAll('.folder-container.archive-folder').forEach(archiveContainer => {
        const hasResults = archiveContainer.querySelector('.file-search-results[style*="display: block"]');
        if (hasResults) {
            const archiveId = archiveContainer.id;
            if (archiveId && archiveId.startsWith('archive-')) {
                // Извлекаем путь архива
                const archivePath = archiveId.replace('archive-', '').replace(/-/g, '/');
                // Проверяем, не был ли архив вручную свернут
                const savedState = localStorage.getItem('archive-' + archivePath);
                if (savedState !== 'collapsed') {
                    const contentDiv = archiveContainer.querySelector('.folder-content');
                    const toggleIcon = archiveContainer.querySelector('.toggle-icon');
                    if (contentDiv) contentDiv.style.display = 'block';
                    if (toggleIcon) toggleIcon.textContent = '▼';
                }
            }
        }
    });
}

searchBtn.addEventListener('click', () => {
    const terms = searchInput.value.trim();
    if (!terms) {
        // Пустой запрос = очистка результатов под файлами
        fetch('/clear_results', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then(() => {
                document.querySelectorAll('.file-search-results').forEach(el => {
                    el.style.display = 'none';
                    el.innerHTML = '';
                });
                updateFilesList();
                refreshIndexStatus();
            });
        return;
    }
    // Запускаем поиск без перестроения индекса
    performSearch(terms);
});

// FR-008: "Удалить файлы" - удаляет загруженные данные и результаты (кнопка "Очистить всё" удалена)
if (deleteFilesBtn) {
    deleteFilesBtn.addEventListener('click', () => {
        if (!confirm('Удалить ВСЕ загруженные файлы и папки, а также сводный файл? Это действие необратимо!')) {
            return;
        }
        
        // Вызываем маршрут для полной очистки
        fetch('/clear_all', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' } 
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Очищаем результаты поиска на UI
                document.querySelectorAll('.file-search-results').forEach(el => {
                    el.style.display = 'none';
                    el.innerHTML = '';
                });
                
                // Обновляем список файлов (покажет пустое дерево)
                updateFilesList();
                refreshIndexStatus();
                
                // Показываем результат
                const message = `Очистка завершена:\n• Удалено элементов: ${data.deleted_count}\n• Индекс удалён: ${data.index_deleted ? 'да' : 'нет'}`;
                if (data.errors && data.errors.length > 0) {
                    const errorList = data.errors.map(e => `  - ${e.path}: ${e.error}`).join('\n');
                    showMessage(message + `\n• Ошибки:\n${errorList}`);
                } else {
                    showMessage(message);
                }
            } else {
                showMessage('Ошибка при очистке: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Ошибка при очистке:', error);
            showMessage('Ошибка при очистке данных');
        });
    });
}

// (Кнопка очистки результатов удалена — очистка выполняется при пустом поисковом запросе)

// --- Build Index auto ---
function rebuildIndexWithProgress() {
    const bar = document.getElementById('indexBuildProgress');
    const fill = document.getElementById('indexBuildFill');
    const text = document.getElementById('indexBuildText');
    if (bar) bar.style.display = 'flex';
    if (fill) fill.style.width = '10%';
    if (text) text.textContent = 'Построение индекса…';
    
    // Запускаем построение индекса с групповой индексацией
    return fetch('/build_index', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_groups: true })
    })
        .then(res => res.json())
        .then(data => {
            if (!data.success) throw new Error(data.message || 'Ошибка построения индекса');
            
            // Запускаем опрос статуса групп
            return pollIndexGroupStatus(fill, text);
        })
        .finally(() => {
            // Не скрываем прогресс после завершения — оставляем 100% и статус
        });
}

// --- Poll Index Group Status (increment-014) ---
function pollIndexGroupStatus(fill, text) {
    return new Promise((resolve, reject) => {
        const maxAttempts = 60; // 60 секунд максимум
        let attempts = 0;
        
        const checkStatus = () => {
            attempts++;
            
            fetch('/index_status')
                .then(res => res.json())
                .then(data => {
                    const status = data.status || 'idle';
                    const groupStatus = data.group_status || {};
                    const currentGroup = data.current_group || '';
                    
                    // Обновляем прогресс-бар и текст
                    let progress = 10;
                    let statusText = 'Построение индекса…';
                    
                    if (groupStatus.fast === 'completed') {
                        progress = 33;
                        statusText = '✅ Быстрые файлы готовы | Поиск доступен';
                    }
                    if (groupStatus.medium === 'completed') {
                        progress = 66;
                        statusText = '✅ DOCX/XLSX готовы | Поиск доступен';
                    }
                    if (groupStatus.slow === 'completed' || status === 'completed') {
                        progress = 100;
                        statusText = '✅ Все файлы обработаны';
                    }
                    
                    // Добавляем индикацию текущей группы
                    if (status === 'running' && currentGroup) {
                        const groupLabels = {
                            'fast': '🔄 Обработка: быстрые файлы (TXT, CSV)',
                            'medium': '🔄 Обработка: средние файлы (DOCX, XLSX, PDF)',
                            'slow': '🔄 Обработка: медленные файлы (OCR, архивы)'
                        };
                        statusText = groupLabels[currentGroup] || statusText;
                    }
                    
                    if (fill) fill.style.width = progress + '%';
                    if (text) text.textContent = statusText;
                    
                    // Обновляем список файлов и статус индекса после каждой группы
                    if (progress >= 33) {
                        refreshIndexStatus();
                        updateFilesList();
                    }
                    
                    // Проверяем завершение
                    if (status === 'completed' || progress === 100) {
                        refreshIndexStatus();
                        updateFilesList();
                        resolve();
                    } else if (status === 'error') {
                        reject(new Error('Ошибка индексации'));
                    } else if (attempts >= maxAttempts) {
                        reject(new Error('Превышено время ожидания'));
                    } else {
                        // Продолжаем опрос каждые 1 секунду
                        setTimeout(checkStatus, 1000);
                    }
                    
                    // Обновляем визуальный индикатор групп
                    updateGroupsIndicator(groupStatus, status);
                })
                .catch(err => {
                    console.error('Ошибка опроса статуса:', err);
                    if (attempts >= maxAttempts) {
                        reject(err);
                    } else {
                        setTimeout(checkStatus, 1000);
                    }
                });
        };
        
        // Первый опрос через 500мс
        setTimeout(checkStatus, 500);
    });
}

// --- Update Groups Indicator (increment-014) ---
function updateGroupsIndicator(groupStatus, indexStatus) {
    const indicator = document.getElementById('groupsIndicator');
    if (!indicator) return;
    
    // Всегда показываем индикатор, чтобы видеть финальный статус групп
    indicator.style.display = 'block';
    
    // Обновляем статусы групп
    const groups = ['fast', 'medium', 'slow'];
    groups.forEach(groupName => {
        const groupDiv = indicator.querySelector(`[data-group="${groupName}"]`);
        if (!groupDiv) return;
        
        const status = groupStatus[groupName] || 'pending';
        const icon = groupDiv.querySelector('.group-icon');
        
        // Удаляем все классы статусов
        groupDiv.classList.remove('pending', 'running', 'completed');
        groupDiv.classList.add(status);
        
        // Обновляем иконку
        if (status === 'completed') {
            icon.textContent = '✅';
        } else if (status === 'running') {
            icon.textContent = '🔄';
        } else {
            icon.textContent = '⏳';
        }
        
        // Время обработки (если доступно в последнем ответе refreshIndexStatus -> сохраним глобально)
        try {
            if (window.__lastIndexStatus && window.__lastIndexStatus.group_times && window.__lastIndexStatus.group_times[groupName]) {
                const gt = window.__lastIndexStatus.group_times[groupName];
                const duration = gt.duration_sec;
                const label = groupDiv.querySelector('.group-label');
                if (label) {
                    if (typeof duration === 'number') {
                        label.textContent = label.textContent.replace(/\s*\(.*?сек\)$/, '');
                        label.textContent += ` (${duration} сек)`;
                    } else if (gt.started_at && gt.completed_at) {
                        // Если duration отсутствует, но есть времена — посчитаем на лету
                        const d = Math.round((new Date(gt.completed_at) - new Date(gt.started_at)) / 1000);
                        if (isFinite(d) && d >= 0) {
                            label.textContent = label.textContent.replace(/\s*\(.*?сек\)$/, '');
                            label.textContent += ` (${d} сек)`;
                        }
                    }
                }
            }
        } catch (_) {}
    });
    
    // Обновляем подсказку
    const hint = document.getElementById('groupsHint');
    if (hint) {
        if (indexStatus === 'completed') {
            hint.textContent = '✅ Индексация завершена! Поиск доступен по всем файлам';
        } else if (groupStatus.fast === 'completed') {
            hint.textContent = '💡 Поиск доступен! Остальные группы обрабатываются в фоне';
        } else {
            hint.textContent = '💡 Поиск будет доступен по мере обработки групп';
        }
    }

    // Авто-повтор поиска при завершении MEDIUM/SLOW, если поиск запускался ранее
    try {
        maybeRerunSearchOnGroupCompletion(groupStatus);
    } catch (_) {}
}

function termsFromInput() {
    const raw = (searchInput && searchInput.value ? searchInput.value : '').trim();
    if (raw) return raw.split(',').map(t => t.trim()).filter(Boolean);
    try {
        const saved = localStorage.getItem('last_search_terms') || '';
        return saved.split(',').map(t => t.trim()).filter(Boolean);
    } catch (_) { return []; }
}

function escapeHtml(s) {
    return s.replace(/[&<>"]+/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
}

function highlightSnippets(terms) {
    const snippets = document.querySelectorAll('.context-snippet');
    if (!terms || terms.length === 0) return;
    snippets.forEach(sn => {
        let html = sn.innerHTML;
        terms.forEach(term => {
            const re = new RegExp('(' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
            html = html.replace(re, '<span class="highlight">$1</span>');
        });
        sn.innerHTML = html;
    });
}

// --- Modal ---
function showMessage(msg) {
    modalMessage.textContent = msg;
    messageModal.style.display = 'flex';
}
closeModal.addEventListener('click', () => messageModal.style.display = 'none');
window.addEventListener('click', (e) => {
    if (e.target === messageModal) messageModal.style.display = 'none';
});

// --- Folder Toggle ---
function toggleFolder(folderName) {
    const folderId = 'folder-' + folderName;
    const folderElement = document.getElementById(folderId);
    const folderContainer = folderElement.closest('.folder-container');
    
    if (folderContainer.classList.contains('collapsed')) {
        folderContainer.classList.remove('collapsed');
        // Сохраняем состояние в localStorage
        localStorage.setItem('folder-' + folderName, 'expanded');
    } else {
        folderContainer.classList.add('collapsed');
        // Сохраняем состояние в localStorage
        localStorage.setItem('folder-' + folderName, 'collapsed');
    }
}

// --- Restore Folder States ---
function restoreFolderStates() {
    const folderContainers = document.querySelectorAll('.folder-container');
    folderContainers.forEach(container => {
        const folderHeader = container.querySelector('.folder-header');
        if (folderHeader) {
            const folderName = folderHeader.querySelector('.folder-name').textContent;
            const savedState = localStorage.getItem('folder-' + folderName);
            
            if (savedState === 'collapsed') {
                container.classList.add('collapsed');
            } else {
                container.classList.remove('collapsed');
            }
        }
    });
    
    // FR-009: Восстанавливаем состояния архивов из localStorage
    const archiveFolders = document.querySelectorAll('.folder-container.archive-folder');
    archiveFolders.forEach(archiveDiv => {
        const archiveId = archiveDiv.id;
        if (archiveId && archiveId.startsWith('archive-')) {
            // Извлекаем путь архива из ID
            const archivePath = archiveId.replace('archive-', '').replace(/-/g, '/');
            const contentDiv = archiveDiv.querySelector('.folder-content');
            const toggleIcon = archiveDiv.querySelector('.toggle-icon');
            
            if (contentDiv) {
                // Попробуем несколько вариантов ключа
                let savedState = localStorage.getItem('archive-' + archivePath);
                
                // Если не нашли - попробуем через оригинальный путь из data-атрибута, если есть
                if (!savedState && archiveDiv.dataset && archiveDiv.dataset.path) {
                    savedState = localStorage.getItem('archive-' + archiveDiv.dataset.path);
                }
                
                if (savedState === 'expanded') {
                    contentDiv.style.display = 'block';
                    if (toggleIcon) toggleIcon.textContent = '▼';
                } else if (savedState === 'collapsed') {
                    contentDiv.style.display = 'none';
                    if (toggleIcon) toggleIcon.textContent = '▶';
                }
            }
        }
    });
}

// --- Initial ---
document.addEventListener('DOMContentLoaded', function() {
    // Инициализируем флаг поиска как false при загрузке страницы
    window.searchWasPerformed = false;
    
    refreshIndexStatus();
    setInterval(refreshIndexStatus, 8000);
    // Первая инициализация списка файлов через API
    updateFilesList().then(() => {
        applyQueryToViewLinks();
    });
});

// --- Index status ---
function refreshIndexStatus() {
    if (!indexStatus) return;
    fetch('/index_status')
        .then(res => res.json())
        .then(data => {
            // Сохраняем последний ответ для использования времени групп
            window.__lastIndexStatus = data;
            if (!data.exists) {
                indexStatus.textContent = 'Сводный файл: не сформирован';
                indexStatus.style.color = '#a00';
            } else {
                const size = (data.size || 0);
                const sizeKb = (size / 1024).toFixed(1);
                const entries = (data.entries == null) ? '—' : data.entries;
                indexStatus.textContent = `Сводный файл: сформирован, ${sizeKb} KB, записей: ${entries}`;
                indexStatus.style.color = '#2a2';
            }
            
            // Обновляем индикатор групп (increment-014)
            if (data.group_status) {
                updateGroupsIndicator(data.group_status, data.status || 'idle');
            }
        })
        .catch(() => {
            indexStatus.textContent = 'Сводный файл: ошибка запроса';
            indexStatus.style.color = '#a00';
        });
}

// --- Helpers: авто-повтор поиска при завершении групп ---
function getActiveSearchTerms() {
    const raw = (searchInput && searchInput.value ? searchInput.value : '').trim();
    if (raw) return raw;
    try {
        return (localStorage.getItem('last_search_terms') || '').trim();
    } catch (_) {
        return '';
    }
}

function maybeRerunSearchOnGroupCompletion(groupStatus) {
    if (!window.searchWasPerformed) return; // поиск не запускался — ничего не делаем
    const terms = getActiveSearchTerms();
    if (!terms) return; // нет терминов — нечего повторять
    // Инициализация памяти состояний
    if (!window.__prevGroupStatus) window.__prevGroupStatus = {};
    if (!window.__autoReran) window.__autoReran = { medium: false, slow: false };
    const prev = window.__prevGroupStatus;
    const current = groupStatus || {};

    // Список групп для авто-повтора
    const targets = ['medium', 'slow'];
    for (const g of targets) {
        const was = prev[g] || 'pending';
        const now = current[g] || 'pending';
        if (!window.__autoReran[g] && was !== 'completed' && now === 'completed') {
            // Триггерим повтор поиска один раз на группу
            try { performSearch(terms); } catch (_) {}
            window.__autoReran[g] = true;
        }
    }
    // Обновляем предыдущее состояние
    window.__prevGroupStatus = { ...current };
}

// --- Append current terms to /view links ---
function applyQueryToViewLinks() {
    const terms = termsFromInput();
    const anchors = document.querySelectorAll('a.result-file-link');
    anchors.forEach(a => {
        try {
            const url = new URL(a.getAttribute('href'), window.location.origin);
            if (terms.length > 0) {
                url.searchParams.set('q', terms.join(','));
            } else {
                url.searchParams.delete('q');
            }
            a.setAttribute('href', url.pathname + (url.search ? url.search : ''));
        } catch (_) {}
    });
}
