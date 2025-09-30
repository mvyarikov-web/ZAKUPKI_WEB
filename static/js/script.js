// --- Drag & Drop ---
// Отключаем выбор одиночных файлов — только папки
const selectFolderBtn = document.getElementById('selectFolderBtn');
const selectedFolderPathEl = document.getElementById('selectedFolderPath');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const filesList = document.getElementById('filesList');
const fileCount = document.getElementById('fileCount');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const clearAllBtn = document.getElementById('clearAllBtn');
// Кнопки построения индекса нет — индекс строится автоматически
const searchResults = document.getElementById('searchResults');
const messageModal = document.getElementById('messageModal');
const modalMessage = document.getElementById('modalMessage');
const closeModal = document.querySelector('.close');
const indexStatus = document.getElementById('indexStatus');

// --- File Select --- (удалено: выбор одиночных файлов)

// --- Folder Select (experimental, works in Chromium browsers) ---
selectFolderBtn.addEventListener('click', () => {
    const folderInput = document.createElement('input');
    folderInput.type = 'file';
    folderInput.webkitdirectory = true;
    folderInput.multiple = true;
    folderInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt,.html,.htm,.csv,.tsv,.xml,.json,.zip,.rar';
    folderInput.style.display = 'none';
    folderInput.addEventListener('change', handleFiles);
    document.body.appendChild(folderInput);
    folderInput.click();
    folderInput.remove();
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
    const allowedExt = new Set(['pdf','doc','docx','xls','xlsx','txt','html','htm','csv','tsv','xml','json','zip','rar']);
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
            // Тихо перестраиваем индекс без модальных сообщений
            return rebuildIndexWithProgress();
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
    // FR-001, FR-009: Обновлённая версия с поддержкой архивов как виртуальных папок
    fetch('/files_json')
        .then(res => res.json())
        .then(data => {
            const { folders = {}, archives = [], file_statuses = {} } = data;
            
            // Создаём карту архивов для быстрого доступа
            const archivesMap = new Map();
            archives.forEach(archive => {
                archivesMap.set(archive.archive_path, archive.contents);
            });
            
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
                
                // Вычисляем агрегированный статус для папки
                const folderStatus = calculateFolderStatus(files, file_statuses, archivesMap);
                
                const headerDiv = document.createElement('div');
                headerDiv.className = 'folder-header';
                headerDiv.onclick = () => toggleFolder(folderName);
                
                headerDiv.innerHTML = `
                    <span class="folder-icon">📁</span>
                    <span class="folder-name">${escapeHtml(folderName)}</span>
                    <span class="file-count-badge">${files.length}</span>
                    <span class="traffic-light traffic-light-${folderStatus}" title="Статус: ${folderStatus}"></span>
                    <button class="delete-folder-btn" title="Удалить папку" onclick="event.stopPropagation(); deleteFolder('${escapeHtml(folderKey)}', '${escapeHtml(folderName)}')">
                        <svg class="icon-trash" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M9 3h6a1 1 0 0 1 1 1v2h4v2h-1v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8H4V6h4V4a1 1 0 0 1 1-1zm1 3h4V5h-4v1zM7 8v12h10V8H7zm3 3h2v7h-2v-7zm4 0h2v7h-2v-7z"></path>
                        </svg>
                    </button>
                    <span class="toggle-icon">${isExpanded ? '▼' : '▶'}</span>
                `;
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'folder-content';
                contentDiv.style.display = isExpanded ? 'block' : 'none';
                
                // Добавляем файлы
                files.forEach(file => {
                    const fileDiv = renderFileItem(file, archivesMap, file_statuses);
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
        })
        .catch(err => {
            console.error('Ошибка загрузки списка файлов:', err);
            // Fallback: используем старый метод
            fetch('/')
                .then(res => res.text())
                .then(html => {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    const newFilesList = doc.getElementById('filesList');
                    if (newFilesList && filesList) {
                        filesList.innerHTML = newFilesList.innerHTML;
                        setTimeout(restoreFolderStates, 100);
                    }
                });
        });
}

function renderFileItem(file, archivesMap, file_statuses) {
    // FR-001, FR-009: Рендер элемента файла или архива
    const fileDiv = document.createElement('div');
    fileDiv.className = 'file-item';
    
    // Получаем статус файла
    const fileStatus = file_statuses[file.path] || {};
    const status = fileStatus.status || 'not_checked';
    const charCount = fileStatus.char_count;
    
    // Определяем цвет светофора
    let trafficLight = 'gray'; // по умолчанию
    if (status === 'contains_keywords') {
        trafficLight = 'green';
    } else if (status === 'no_keywords') {
        trafficLight = 'red';
    } else if (status === 'error' || status === 'unsupported') {
        trafficLight = 'gray';
    }
    
    // Проверяем, является ли файл архивом
    if (file.is_archive && archivesMap.has(file.path)) {
        // Это архив - отображаем как раскрываемую папку
        const archiveContents = archivesMap.get(file.path);
        fileDiv.className = 'file-item archive-item';
        
        // Вычисляем агрегированный статус для архива
        const archiveStatus = calculateArchiveStatus(archiveContents, file_statuses);
        
        const archiveHeaderDiv = document.createElement('div');
        archiveHeaderDiv.className = 'file-info archive-header';
        archiveHeaderDiv.style.cursor = 'pointer';
        archiveHeaderDiv.onclick = () => toggleArchive(file.path);
        
        archiveHeaderDiv.innerHTML = `
            <span class="folder-icon">📦</span>
            <div class="file-details">
                <span class="file-name">${escapeHtml(file.name)}</span>
                <span class="file-size">${(file.size / 1024).toFixed(1)} KB</span>
                <span class="archive-badge">Архив (${archiveContents.length} элементов)</span>
            </div>
            <span class="traffic-light traffic-light-${archiveStatus}" title="Статус архива: ${archiveStatus}"></span>
            <span class="toggle-icon archive-toggle">▶</span>
        `;
        
        const archiveContentDiv = document.createElement('div');
        archiveContentDiv.className = 'archive-content';
        archiveContentDiv.id = `archive-${file.path.replace(/[^a-zA-Z0-9]/g, '-')}`;
        archiveContentDiv.style.display = 'none';
        archiveContentDiv.style.marginLeft = '30px';
        
        // Добавляем содержимое архива
        archiveContents.forEach(entry => {
            if (entry.status === 'error') {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'file-item file-disabled';
                errorDiv.innerHTML = `
                    <div class="file-info">
                        <span class="file-icon">⚠️</span>
                        <div class="file-details">
                            <span class="file-name">${escapeHtml(entry.name || file.name)}</span>
                            <span class="file-error text-danger">${escapeHtml(entry.error || 'Ошибка')}</span>
                        </div>
                    </div>
                `;
                archiveContentDiv.appendChild(errorDiv);
            } else if (entry.is_virtual_folder) {
                // Виртуальная папка внутри архива
                const folderDiv = document.createElement('div');
                folderDiv.className = 'file-item virtual-folder';
                folderDiv.innerHTML = `
                    <div class="file-info">
                        <span class="folder-icon">📁</span>
                        <div class="file-details">
                            <span class="file-name">${escapeHtml(entry.name)}</span>
                        </div>
                    </div>
                `;
                archiveContentDiv.appendChild(folderDiv);
            } else {
                // Обычный файл внутри архива
                const entryDiv = document.createElement('div');
                entryDiv.className = 'file-item';
                const icon = entry.is_archive ? '📦' : '📄';
                
                // Получаем статус для файла из архива
                const entryStatus = file_statuses[entry.path] || {};
                const entryTrafficLight = getTrafficLightColor(entryStatus.status || 'not_checked');
                const entryCharCount = entryStatus.char_count;
                
                entryDiv.innerHTML = `
                    <div class="file-info">
                        <span class="file-icon">${icon}</span>
                        <div class="file-details">
                            <a class="file-name result-file-link" href="/download/${encodeURIComponent(entry.path)}" target="_blank" rel="noopener">${escapeHtml(entry.name)}</a>
                            <span class="file-size">${(entry.size / 1024).toFixed(1)} KB</span>
                            ${entryCharCount !== undefined ? `<span class="file-chars">Символов: ${entryCharCount}</span>` : ''}
                        </div>
                    </div>
                    <span class="traffic-light traffic-light-${entryTrafficLight}" title="Статус: ${entryStatus.status || 'not_checked'}"></span>
                `;
                archiveContentDiv.appendChild(entryDiv);
            }
        });
        
        fileDiv.appendChild(archiveHeaderDiv);
        fileDiv.appendChild(archiveContentDiv);
    } else {
        // Обычный файл
        const icon = file.is_archive ? '📦' : '📄';
        fileDiv.innerHTML = `
            <div class="file-info">
                <span class="file-icon">${icon}</span>
                <div class="file-details">
                    <a class="file-name result-file-link" href="/download/${encodeURIComponent(file.path)}" target="_blank" rel="noopener">${escapeHtml(file.name)}</a>
                    <span class="file-size">${(file.size / 1024).toFixed(1)} KB</span>
                    ${charCount !== undefined ? `<span class="file-chars${charCount === 0 ? ' text-danger' : ''}">Символов: ${charCount}</span>` : ''}
                    ${fileStatus.error ? `<span class="file-error text-danger">${escapeHtml(fileStatus.error)}</span>` : ''}
                </div>
            </div>
            <div class="file-status">
                <span class="traffic-light traffic-light-${trafficLight}" title="Статус: ${status}"></span>
                <button class="delete-btn" title="Удалить файл" onclick="deleteFile('${escapeHtml(file.path)}')">
                    <svg class="icon-trash" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M9 3h6a1 1 0 0 1 1 1v2h4v2h-1v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8H4V6h4V4a1 1 0 0 1 1-1zm1 3h4V5h-4v1zM7 8v12h10V8H7zm3 3h2v7h-2v-7zm4 0h2v7h-2v-7z"></path>
                    </svg>
                </button>
            </div>
        `;
    }
    
    return fileDiv;
}

function toggleArchive(archivePath) {
    // FR-009: Переключение отображения содержимого архива
    const archiveId = `archive-${archivePath.replace(/[^a-zA-Z0-9]/g, '-')}`;
    const contentDiv = document.getElementById(archiveId);
    const toggleIcon = event.currentTarget.querySelector('.archive-toggle');
    
    if (contentDiv) {
        const isHidden = contentDiv.style.display === 'none';
        contentDiv.style.display = isHidden ? 'block' : 'none';
        if (toggleIcon) {
            toggleIcon.textContent = isHidden ? '▼' : '▶';
        }
    }
}

// Helper function to get traffic light color based on status
function getTrafficLightColor(status) {
    if (status === 'contains_keywords') return 'green';
    if (status === 'no_keywords') return 'red';
    if (status === 'error' || status === 'unsupported') return 'gray';
    return 'gray'; // not_checked or unknown
}

// Calculate folder status based on files inside
function calculateFolderStatus(files, file_statuses, archivesMap) {
    let hasGreen = false;
    let hasRed = false;
    
    for (const file of files) {
        const fileStatus = file_statuses[file.path] || {};
        const status = fileStatus.status || 'not_checked';
        
        if (status === 'contains_keywords') {
            hasGreen = true;
        } else if (status === 'no_keywords') {
            hasRed = true;
        }
        
        // Если это архив, проверяем его содержимое
        if (file.is_archive && archivesMap.has(file.path)) {
            const archiveContents = archivesMap.get(file.path);
            for (const entry of archiveContents) {
                const entryStatus = file_statuses[entry.path] || {};
                if (entryStatus.status === 'contains_keywords') {
                    hasGreen = true;
                } else if (entryStatus.status === 'no_keywords') {
                    hasRed = true;
                }
            }
        }
    }
    
    // Логика: зелёный если есть хотя бы одно совпадение, красный если все проверены и нет совпадений, серый иначе
    if (hasGreen) return 'green';
    if (hasRed) return 'red';
    return 'gray';
}

// Calculate archive status based on its contents
function calculateArchiveStatus(archiveContents, file_statuses) {
    let hasGreen = false;
    let hasRed = false;
    
    for (const entry of archiveContents) {
        if (entry.status === 'error' || entry.is_virtual_folder) continue;
        
        const entryStatus = file_statuses[entry.path] || {};
        const status = entryStatus.status || 'not_checked';
        
        if (status === 'contains_keywords') {
            hasGreen = true;
        } else if (status === 'no_keywords') {
            hasRed = true;
        }
    }
    
    if (hasGreen) return 'green';
    if (hasRed) return 'red';
    return 'gray';
}

// --- Delete File ---
function deleteFile(filename) {
    if (!confirm('Удалить файл ' + filename + '?')) return;
    
    // Правильное кодирование имени файла для URL
    const encodedFilename = encodeURIComponent(filename);
    console.log('Удаляем файл:', filename, 'Закодированный:', encodedFilename);
    
    fetch('/delete/' + encodedFilename, {
        method: 'DELETE'
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showMessage('Файл удалён. Перестраиваем индекс…');
            return rebuildIndexWithProgress().then(() => {
                showMessage('Индекс перестроен');
                updateFilesList();
                refreshSearchResultsIfActive();
            });
        } else {
            showMessage(data.error || 'Ошибка удаления файла');
        }
    })
    .catch(error => {
        console.error('Ошибка при удалении файла:', error);
        showMessage('Ошибка удаления файла');
    });
}

// --- Delete Folder ---
function deleteFolder(folderKey, folderDisplayName) {
    const confirmMessage = folderKey === 'root' 
        ? `Удалить ВСЕ файлы из корневой папки? Это действие необратимо!`
        : `Удалить папку "${folderDisplayName}" и все файлы в ней? Это действие необратимо!`;
        
    if (!confirm(confirmMessage)) return;
    
    console.log('Удаляем папку:', folderKey, 'Отображаемое имя:', folderDisplayName);
    
    const encodedFolderPath = encodeURIComponent(folderKey);
    
    fetch('/delete_folder/' + encodedFolderPath, {
        method: 'DELETE'
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Без дополнительных сообщений: молча перестраиваем индекс и обновляем список файлов
            return rebuildIndexWithProgress().then(() => {
                updateFilesList();
                refreshSearchResultsIfActive();
            });
        } else {
            showMessage(data.error || 'Ошибка удаления папки');
        }
    })
    .catch(error => {
        console.error('Ошибка при удалении папки:', error);
        showMessage('Ошибка удаления папки');
    });
}

// --- Search ---
function performSearch(terms) {
    searchResults.style.display = 'block';
    searchResults.innerHTML = '<div>Поиск...</div>';
    return fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_terms: terms })
    })
    .then(res => res.json())
    .then(data => {
        try { localStorage.setItem('last_search_terms', terms); } catch (e) {}
        // Критично: сразу обновляем список файлов, чтобы светофоры отобразились на первом поиске
        updateFilesList();
        if (data.results && data.results.length > 0) {
            searchResults.innerHTML = '';
            const t = termsFromInput();
            data.results.forEach(result => {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                
                // Улучшенная логика для отображения пути (включая архивы)
                const hasPath = !!result.path;
                let breadcrumb = '';
                
                if (result.source && result.source.includes('://')) {
                    // Это файл из архива (формат: zip://archive.zip/path/to/file.txt)
                    const parts = result.source.split('://');
                    if (parts.length === 2) {
                        const [protocol, fullPath] = parts;
                        const pathParts = fullPath.split('/');
                        const archiveName = pathParts[0];
                        const innerPath = pathParts.slice(1).join(' › ');
                        breadcrumb = `${archiveName} › ${innerPath}`;
                    } else {
                        breadcrumb = result.source;
                    }
                } else if (hasPath && result.path.includes('/')) {
                    // Обычный файл в подпапке
                    const pathParts = result.path.split('/');
                    breadcrumb = pathParts.slice(0, -1).join(' › ') || 'Загруженные файлы';
                } else {
                    breadcrumb = 'Загруженные файлы';
                }
                
                const fileNameHtml = hasPath
                    ? `<a class="result-file-link" href="/view/${encodeURIComponent(result.path)}?q=${encodeURIComponent(t.join(','))}" target="_blank" rel="noopener">${escapeHtml(result.filename)}</a>`
                    : `${escapeHtml(result.filename)}`;
                
                // Рендер по каждому термину: количество и до 3 сниппетов
                const perTermHtml = (result.per_term || []).map(entry => {
                    const snips = (entry.snippets || []).slice(0,3).map(s => `<div class="context-snippet">${escapeHtml(s)}</div>`).join('');
                    return `<div class="per-term-block">
                        <div class="found-terms"><span class="found-term">${escapeHtml(entry.term)} (${entry.count})</span></div>
                        <div class="context-snippets">${snips || '<div class="context-empty">Нет сниппетов</div>'}</div>
                    </div>`;
                }).join('');
                item.innerHTML = `
                    <div class="result-header">
                        <span class="result-folder">${escapeHtml(breadcrumb)}</span>
                        <span class="result-filename" title="Источник: ${escapeHtml(result.source || '')}">${fileNameHtml}</span>
                    </div>
                    ${perTermHtml}
                `;
                searchResults.appendChild(item);
            });
            highlightSnippets(t);
            applyQueryToViewLinks();
        } else {
            searchResults.innerHTML = '<div>Ничего не найдено по этим ключевым словам.</div>';
        }
    })
    .catch(() => {
        searchResults.innerHTML = '<div>Ошибка поиска.</div>';
    });
}

function refreshSearchResultsIfActive() {
    const terms = searchInput.value.trim();
    if (!terms) {
        // если запрос пуст — просто скрываем блок
        searchResults.style.display = 'none';
        searchResults.innerHTML = '';
        return;
    }
    if (searchResults && searchResults.style.display !== 'none') {
        // пере запускаем поиск, чтобы убрать удалённые документы из выдачи
        performSearch(terms);
    }
}

searchBtn.addEventListener('click', () => {
    const terms = searchInput.value.trim();
    if (!terms) {
        // Пустой запрос = очистка результатов
        fetch('/clear_results', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then(() => {
                searchResults.style.display = 'none';
                updateFilesList();
                refreshIndexStatus();
            });
        return;
    }
    // Запускаем поиск без перестроения индекса
    searchResults.style.display = 'block';
    performSearch(terms);
});

// Clear All button handler
if (clearAllBtn) {
    clearAllBtn.addEventListener('click', () => {
        // Очищаем поисковую строку
        searchInput.value = '';
        
        // Очищаем результаты поиска
        searchResults.style.display = 'none';
        searchResults.innerHTML = '';
        
        // Очищаем состояние на сервере
        fetch('/clear_results', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then(() => {
                // Удаляем подсветку из сниппетов (если есть)
                document.querySelectorAll('.highlight').forEach(el => {
                    const text = el.textContent;
                    el.replaceWith(document.createTextNode(text));
                });
                
                // Обновляем список файлов (сбросит светофоры)
                updateFilesList();
                refreshIndexStatus();
                
                // Очищаем localStorage
                try {
                    localStorage.removeItem('last_search_terms');
                } catch (e) {}
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
    return fetch('/build_index', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (!data.success) throw new Error(data.message || 'Ошибка построения индекса');
            if (fill) fill.style.width = '100%';
            if (text) text.textContent = 'Готово';
            refreshIndexStatus();
            updateFilesList();
        })
        .finally(() => {
            setTimeout(() => { if (bar) bar.style.display = 'none'; if (fill) fill.style.width = '0%'; }, 600);
        });
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
}

// --- Initial ---
document.addEventListener('DOMContentLoaded', function() {
    refreshIndexStatus();
    setInterval(refreshIndexStatus, 8000);
    applyQueryToViewLinks();
});

// --- Index status ---
function refreshIndexStatus() {
    if (!indexStatus) return;
    fetch('/index_status')
        .then(res => res.json())
        .then(data => {
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
        })
        .catch(() => {
            indexStatus.textContent = 'Сводный файл: ошибка запроса';
            indexStatus.style.color = '#a00';
        });
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
