// --- Drag & Drop ---
// Отключаем выбор одиночных файлов — только папки

// Вспомогательная функция для безопасного парсинга JSON из fetch
function safeFetchJson(response) {
    if (!response.ok) {
        // Пытаемся распарсить JSON даже при ошибке
        return response.json().catch(() => {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }).then(data => {
            throw new Error(data.error || data.message || `Ошибка ${response.status}`);
        });
    }
    return response.json();
}

const selectFolderBtn = document.getElementById('selectFolderBtn');
const selectedFolderPathEl = document.getElementById('selectedFolderPath');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const filesList = document.getElementById('filesList');
const fileCount = document.getElementById('fileCount');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const excludeModeToggle = document.getElementById('excludeModeToggle');
const toggleLabel = document.getElementById('toggleLabel');
// FR-008: Удалена кнопка clearAllBtn - только deleteFilesBtn
const deleteFilesBtn = document.getElementById('deleteFilesBtn');
// Кнопки построения индекса нет — индекс строится автоматически
const messageModal = document.getElementById('messageModal');
const modalMessage = document.getElementById('modalMessage');
const closeModal = document.querySelector('.close');
const indexStatus = document.getElementById('indexStatus');

// --- Exclude Mode Toggle (FR-009) ---
if (excludeModeToggle && toggleLabel) {
    excludeModeToggle.addEventListener('change', () => {
        if (excludeModeToggle.checked) {
            toggleLabel.textContent = 'Не содержит';
            toggleLabel.classList.add('exclude-mode');
        } else {
            toggleLabel.textContent = 'Содержит';
            toggleLabel.classList.remove('exclude-mode');
        }
    });
}

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
    .then(safeFetchJson)
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
    return fetch('/files_json')
        .then(safeFetchJson)
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
        const searchPerformed = (window.searchWasPerformed === true);
        // Папка до первого поиска должна быть серой, поэтому если поиск не выполнялся — принудительно используем gray
        const folderStatus = searchPerformed ? calculateFolderStatus(files, file_statuses, archivesMap, searchPerformed) : 'gray';
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

function renderFileItem(file, archivesMap, file_statuses) {
    // FR-001, FR-009: Рендер элемента файла или архива
    const fileDiv = document.createElement('div');
    fileDiv.className = 'file-item';
    
    // Получаем статус файла
    const fileStatus = file_statuses[file.path] || {};
    const status = fileStatus.status || 'not_checked';
    const charCount = fileStatus.char_count;
    
    // FR-005: Определяем цвет светофора
    // Проверяем, есть ли результаты поиска и был ли поиск
    const hasSearchResults = window.TrafficLights.hasSearchResultsForFile(file.path);
    const searchPerformed = window.TrafficLights.isSearchPerformed();
    let trafficLight = window.TrafficLights.getFileTrafficLightColor(status, charCount, hasSearchResults, searchPerformed);

    
    // Проверяем, является ли файл архивом
    if (file.is_archive && archivesMap.has(file.path)) {
        // FR-008: Это архив - отображаем как раскрываемую папку со словом "Архив" в названии
        const archiveContents = archivesMap.get(file.path);
        fileDiv.className = 'folder-container archive-folder';
        fileDiv.id = `archive-${file.path.replace(/[^a-zA-Z0-9]/g, '-')}`;
        fileDiv.dataset.path = file.path; // FR-009: Сохраняем путь для localStorage
        
    // Вычисляем агрегированный статус для архива; до первого поиска всегда серый
    const archiveStatus = searchPerformed ? calculateArchiveStatus(archiveContents, file_statuses, searchPerformed) : 'gray';
        
        // Проверяем сохранённое состояние архива
        const savedArchiveState = localStorage.getItem('archive-' + file.path);
        const isArchiveExpanded = savedArchiveState !== 'collapsed'; // По умолчанию развернуто
        
        const archiveHeaderDiv = document.createElement('div');
        archiveHeaderDiv.className = 'folder-header';
        archiveHeaderDiv.onclick = () => toggleArchive(file.path);
        
        // FR-008: В названии добавляем слово "Архив", отображаем как обычную папку
        const archiveName = file.name.replace(/\.(zip|rar)$/i, '');
        archiveHeaderDiv.innerHTML = `
            <span class="folder-icon">📁</span>
            <span class="folder-name">${escapeHtml(archiveName)} (Архив)</span>
            <span class="file-count-badge">${archiveContents.length}</span>
            <span class="traffic-light traffic-light-${archiveStatus}" title="Статус: ${archiveStatus}"></span>
            <button class="delete-btn" title="Удалить архив" onclick="event.stopPropagation(); deleteFile('${escapeHtml(file.path)}')">
                <svg class="icon-trash" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M9 3h6a1 1 0 0 1 1 1v2h4v2h-1v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8H4V6h4V4a1 1 0 0 1 1-1zm1 3h4V5h-4v1zM7 8v12h10V8H7zm3 3h2v7h-2v-7zm4 0h2v7h-2v-7z"></path>
                </svg>
            </button>
            <span class="toggle-icon">${isArchiveExpanded ? '▼' : '▶'}</span>
        `;
        
        const archiveContentDiv = document.createElement('div');
        archiveContentDiv.className = 'folder-content';
        archiveContentDiv.style.display = isArchiveExpanded ? 'block' : 'none';
        
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
                // Обычный файл внутри архива - тоже нужен контейнер для результатов поиска
                const entryDiv = document.createElement('div');
                entryDiv.className = 'file-item-wrapper';
                entryDiv.setAttribute('data-file-path', entry.path);
                
                const icon = entry.is_archive ? '📦' : '📄';
                
                // Получаем статус для файла из архива
                const entryStatus = file_statuses[entry.path] || {};
                const entryCharCount = entryStatus.char_count || 0;
                const entryHasResults = window.TrafficLights.hasSearchResultsForFile(entry.path);
                const entryTrafficLight = window.TrafficLights.getFileTrafficLightColor(entryStatus.status || 'not_checked', entryCharCount, entryHasResults, searchPerformed);
                const isUnreadable = (entryStatus.status === 'unsupported') || (entryStatus.status === 'error') || (entryCharCount === 0);
                
                entryDiv.innerHTML = `
                    <div class="file-item${isUnreadable ? ' file-disabled' : ''}">
                        <div class="file-info">
                            <span class="file-icon">${icon}</span>
                            <div class="file-details">
                                ${isUnreadable ? 
                                    `<span class="file-name" title="Файл недоступен для просмотра/скачивания">${escapeHtml(entry.name)}</span>` :
                                    `<a class="file-name result-file-link" href="/view/${encodeURIComponent(entry.path)}" target="_blank" rel="noopener">${escapeHtml(entry.name)}</a>`
                                }
                                <span class="file-size">${(entry.size / 1024).toFixed(1)} KB</span>
                                ${entryCharCount !== undefined ? `<span class="file-chars${entryCharCount === 0 ? ' text-danger' : ''}">Символов: ${entryCharCount}</span>` : ''}
                                ${entryStatus.error ? `<span class="file-error text-danger">${escapeHtml(entryStatus.error)}</span>` : ''}
                                ${entryStatus.status === 'unsupported' ? `<span class="file-error text-danger">Неподдерживаемый формат</span>` : ''}
                            </div>
                        </div>
                        <span class="traffic-light traffic-light-${entryTrafficLight}" data-status="${entryStatus.status || 'not_checked'}" data-chars="${entryCharCount}" title="Статус: ${entryStatus.status || 'not_checked'}"></span>
                    </div>
                    <!-- Контейнер для результатов поиска под файлом из архива -->
                    <div class="file-search-results" style="display:none;"></div>
                `;
                archiveContentDiv.appendChild(entryDiv);
            }
        });
        
        fileDiv.appendChild(archiveHeaderDiv);
        fileDiv.appendChild(archiveContentDiv);
    } else {
        // Обычный файл - создаем обертку для поддержки результатов поиска
        fileDiv.className = 'file-item-wrapper';
        fileDiv.setAttribute('data-file-path', file.path);
        
        // Пересчитываем светофор для обычного файла с учетом поиска
        trafficLight = window.TrafficLights.getFileTrafficLightColor(status, charCount, hasSearchResults, searchPerformed);
        
        const icon = file.is_archive ? '📦' : '📄';
        const isUnreadable = (status === 'unsupported') || (status === 'error') || (charCount !== undefined && charCount === 0);
        
        fileDiv.innerHTML = `
            <div class="file-item${isUnreadable ? ' file-disabled' : ''}">
                <div class="file-info">
                    <span class="file-icon">${icon}</span>
                    <div class="file-details">
                        ${isUnreadable ? 
                            `<span class="file-name" title="Файл недоступен для просмотра/скачивания">${escapeHtml(file.name)}</span>` :
                            `<a class="file-name result-file-link" href="/view/${encodeURIComponent(file.path)}" target="_blank" rel="noopener">${escapeHtml(file.name)}</a>`
                        }
                        <span class="file-size">${(file.size / 1024).toFixed(1)} KB</span>
                        ${charCount !== undefined ? `<span class="file-chars${charCount === 0 ? ' text-danger' : ''}">Символов: ${charCount}</span>` : ''}
                        ${fileStatus.error ? `<span class="file-error text-danger">${escapeHtml(fileStatus.error)}</span>` : ''}
                        ${status === 'unsupported' ? `<span class="file-error text-danger">Неподдерживаемый формат</span>` : ''}
                    </div>
                </div>
                <div class="file-status">
                    <span class="traffic-light traffic-light-${trafficLight}" data-status="${status}" data-chars="${charCount ?? ''}" title="Статус: ${status}"></span>
                    <button class="delete-btn" title="Удалить файл" onclick="deleteFile('${escapeHtml(file.path)}')">
                        <svg class="icon-trash" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M9 3h6a1 1 0 0 1 1 1v2h4v2h-1v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8H4V6h4V4a1 1 0 0 1 1-1zm1 3h4V5h-4v1zM7 8v12h10V8H7zm3 3h2v7h-2v-7zm4 0h2v7h-2v-7z"></path>
                        </svg>
                    </button>
                </div>
            </div>
            <!-- FR-003, FR-004, FR-005: Контейнер для результатов поиска под файлом -->
            <div class="file-search-results" style="display:none;"></div>
        `;
    }
    
    return fileDiv;
}

function toggleArchive(archivePath) {
    // FR-008, FR-009: Переключение отображения содержимого архива (как обычная папка)
    const archiveId = `archive-${archivePath.replace(/[^a-zA-Z0-9]/g, '-')}`;
    const archiveDiv = document.getElementById(archiveId);
    
    if (archiveDiv) {
        const contentDiv = archiveDiv.querySelector('.folder-content');
        const toggleIcon = event.currentTarget.querySelector('.toggle-icon');
        
        if (contentDiv) {
            const isHidden = contentDiv.style.display === 'none';
            contentDiv.style.display = isHidden ? 'block' : 'none';
            if (toggleIcon) {
                toggleIcon.textContent = isHidden ? '▼' : '▶';
            }
            // FR-009: Сохраняем состояние архива в localStorage
            try {
                localStorage.setItem('archive-' + archivePath, isHidden ? 'expanded' : 'collapsed');
            } catch (e) {
                console.warn('Не удалось сохранить состояние архива в localStorage', e);
            }
        }
    }
}

// FR-005: Helper function to get traffic light color based on status
// Используем централизованную логику из модуля traffic-lights.js
function getTrafficLightColor(status, charCount = null, hasSearchResults = false, searchPerformed = false) {
    return window.TrafficLights.getFileTrafficLightColor(status, charCount, hasSearchResults, searchPerformed);
}

// FR-006, FR-007: Calculate folder status based on files inside
// Логика: используем централизованную логику из модуля traffic-lights.js
function calculateFolderStatus(files, file_statuses, archivesMap, searchPerformed = false) {
    const fileColors = [];
    
    for (const file of files) {
        const fileStatus = file_statuses[file.path] || {};
        const status = fileStatus.status || 'not_checked';
        const charCount = fileStatus.char_count || 0;
        
        // Проверяем, есть ли результаты поиска для этого файла
        const hasSearchResults = window.TrafficLights.hasSearchResultsForFile(file.path);
        
        const lightColor = window.TrafficLights.getFileTrafficLightColor(status, charCount, hasSearchResults, searchPerformed);
        fileColors.push(lightColor);
        
        // FR-006: Если это архив, проверяем его содержимое
        if (file.is_archive && archivesMap.has(file.path)) {
            const archiveContents = archivesMap.get(file.path);
            for (const entry of archiveContents) {
                const entryStatus = file_statuses[entry.path] || {};
                const entryCharCount = entryStatus.char_count || 0;
                
                const entryHasResults = window.TrafficLights.hasSearchResultsForFile(entry.path);
                const entryLightColor = window.TrafficLights.getFileTrafficLightColor(entryStatus.status || 'not_checked', entryCharCount, entryHasResults, searchPerformed);
                fileColors.push(entryLightColor);
            }
        }
    }
    
    return window.TrafficLights.getFolderTrafficLightColor(fileColors);
}

// FR-006: Calculate archive status based on its contents
// Логика: используем централизованную логику из модуля traffic-lights.js
function calculateArchiveStatus(archiveContents, file_statuses, searchPerformed = false) {
    const fileColors = [];
    
    for (const entry of archiveContents) {
        const entryStatus = file_statuses[entry.path] || {};
        const entryCharCount = entryStatus.char_count || 0;
        
        // Проверяем, есть ли результаты поиска для этого файла
        const entryHasResults = window.TrafficLights.hasSearchResultsForFile(entry.path);
        
        const lightColor = window.TrafficLights.getFileTrafficLightColor(entryStatus.status || 'not_checked', entryCharCount, entryHasResults, searchPerformed);
        fileColors.push(lightColor);
    }
    
    return window.TrafficLights.getFolderTrafficLightColor(fileColors);
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
    .then(safeFetchJson)
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
    .then(safeFetchJson)
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

// Функция обновления светофоров после поиска
function updateTrafficLightsAfterSearch() {
    const searchPerformed = window.TrafficLights.isSearchPerformed();
    console.log('🔍 updateTrafficLightsAfterSearch: searchPerformed =', searchPerformed);
    
    // Обновляем светофоры для всех файлов
    document.querySelectorAll('.file-item').forEach(fileItem => {
        const fileWrapper = fileItem.closest('.file-item-wrapper');
        if (!fileWrapper) return;
        
        const filePath = fileWrapper.getAttribute('data-file-path');
        if (!filePath) return;
        
        const trafficLight = fileItem.querySelector('.traffic-light');
        if (!trafficLight) return;
        
        // Читаем статус из data-атрибутов светофора (они устанавливаются при рендере)
        let status = trafficLight.getAttribute('data-status') || 'not_checked';
        let charCount = parseInt(trafficLight.getAttribute('data-chars') || '0', 10);
        
        // Если data-атрибуты пустые, пытаемся определить из DOM
        if (!status || status === 'not_checked') {
            const hasError = fileItem.querySelector('.file-error');
            const isDisabled = fileItem.classList.contains('file-disabled');
            
            if (hasError || isDisabled) {
                const errorText = hasError ? hasError.textContent : '';
                if (errorText.includes('Неподдерживаемый формат')) {
                    status = 'unsupported';
                } else {
                    status = 'error';
                }
                charCount = 0;
            } else {
                // Извлекаем char_count из .file-chars
                const charsEl = fileItem.querySelector('.file-chars');
                if (charsEl && charsEl.textContent) {
                    const m = charsEl.textContent.match(/(\d+)/);
                    if (m) {
                        charCount = parseInt(m[1], 10);
                        if (charCount > 0) {
                            status = 'contains_keywords'; // Файл проиндексирован
                        } else {
                            status = 'error'; // Нулевой объём = ошибка
                        }
                    }
                }
            }
        }
        
        // Проверяем результаты поиска
        const hasSearchResults = window.TrafficLights.hasSearchResultsForFile(filePath);
        
        // Определяем новый цвет светофора
        const newColor = window.TrafficLights.getFileTrafficLightColor(status, charCount, hasSearchResults, searchPerformed);
        
        // Отладочная информация
        console.log(`🚦 Файл: ${filePath}, статус: ${status}, символов: ${charCount}, есть результаты: ${hasSearchResults}, цвет: ${newColor}`);
        
        // Обновляем светофор
        trafficLight.className = `traffic-light traffic-light-${newColor}`;
        // Обновляем data-атрибуты для последующих пересчётов
        trafficLight.setAttribute('data-status', status);
        trafficLight.setAttribute('data-chars', charCount.toString());
    });
    
    // Обновляем светофоры для папок и архивов
    document.querySelectorAll('.folder-container').forEach(folderContainer => {
        const folderHeader = folderContainer.querySelector('.folder-header');
        if (!folderHeader) return;
        
        const folderContent = folderContainer.querySelector('.folder-content');
        if (!folderContent) return;
        
        // Собираем цвета файлов в папке
        const fileColors = [];
        folderContent.querySelectorAll('.file-item .traffic-light').forEach(light => {
            const color = light.classList.contains('traffic-light-red') ? 'red' :
                         light.classList.contains('traffic-light-green') ? 'green' :
                         light.classList.contains('traffic-light-yellow') ? 'yellow' : 'gray';
            fileColors.push(color);
        });
        
        // Определяем цвет папки
        const folderColor = window.TrafficLights.getFolderTrafficLightColor(fileColors);
        
        // Обновляем светофор папки
        const folderTrafficLight = folderHeader.querySelector('.traffic-light');
        if (folderTrafficLight) {
            folderTrafficLight.className = `traffic-light traffic-light-${folderColor}`;
        }
    });
}

async function performSearch(terms) {
    // FR-003: Убираем отдельную секцию результатов - результаты будут под файлами
    // Очищаем все предыдущие результаты под файлами
    document.querySelectorAll('.file-search-results').forEach(el => {
        el.style.display = 'none';
        el.innerHTML = '';
    });
    document.querySelectorAll('.file-item-wrapper[data-has-results]')
        .forEach(w => w.removeAttribute('data-has-results'));
    
    // Устанавливаем глобальный флаг, что поиск был выполнен
    window.searchWasPerformed = true;
    
    const excludeMode = excludeModeToggle && excludeModeToggle.checked;
    
    const resp = await fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            search_terms: terms,
            exclude_mode: excludeMode 
        })
    });
    const data = await resp.json();
    try { localStorage.setItem('last_search_terms', terms); } catch (e) {}
    // Критично: сначала обновляем список файлов и дожидаемся рендера, чтобы не потерять результаты
    await updateFilesList();
    
    if (data.results && data.results.length > 0) {
            const t = termsFromInput();
            
            // FR-004, FR-005: Группируем результаты по файлам и отображаем под каждым файлом
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
                        // FR-004, FR-009: До 2 сниппетов на термин (или 1 в режиме exclude)
                        const isExcludeMode = excludeModeToggle && excludeModeToggle.checked;
                        const maxSnippets = isExcludeMode ? 1 : 2;
                        
                        const perTermHtml = resultsByFile[filePath].perTerm.map(entry => {
                            const snips = (entry.snippets || []).slice(0, maxSnippets).map(s => 
                                `<div class="context-snippet">${escapeHtml(s)}</div>`
                            ).join('');
                            
                            // FR-009: Если термин начинается с "не содержит:", выделяем префикс красным
                            let termHtml;
                            if (entry.term.startsWith('не содержит:')) {
                                const parts = entry.term.split(':');
                                termHtml = `<span class="exclude-prefix">${escapeHtml(parts[0])}:</span> ${escapeHtml(parts.slice(1).join(':').trim())}`;
                            } else {
                                termHtml = `${escapeHtml(entry.term)} (${entry.count})`;
                            }
                            
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
            
            // Обновляем светофоры после установки результатов
            updateTrafficLightsAfterSearch();
            
            // Сортировка: файлы с результатами наверх, проиндексированные в середине, неиндексированные вниз
            document.querySelectorAll('.folder-content').forEach(contentDiv => {
                const wrappers = Array.from(contentDiv.querySelectorAll(':scope > .file-item-wrapper, :scope > .file-item, :scope > .folder-container.archive-folder'));
                
                const scored = wrappers.map(el => {
                    // Получаем фактический цвет светофора из DOM
                    const trafficLight = el.querySelector('.traffic-light');
                    let lightColor = window.TrafficLights.COLORS.GRAY;
                    
                    if (trafficLight) {
                        if (trafficLight.classList.contains('traffic-light-red')) {
                            lightColor = window.TrafficLights.COLORS.RED;
                        } else if (trafficLight.classList.contains('traffic-light-green')) {
                            lightColor = window.TrafficLights.COLORS.GREEN;
                        } else if (trafficLight.classList.contains('traffic-light-yellow')) {
                            lightColor = window.TrafficLights.COLORS.YELLOW;
                        } else if (trafficLight.classList.contains('traffic-light-gray')) {
                            lightColor = window.TrafficLights.COLORS.GRAY;
                        }
                    }
                    
                    const score = window.TrafficLights.getTrafficLightSortPriority(lightColor);
                    return { el, score };
                });
                
                scored.sort((a, b) => b.score - a.score);
                scored.forEach(({ el }) => contentDiv.appendChild(el));
            });

            // Раскрываем папки с результатами, если они не были вручную свернуты
            expandFoldersWithResults();

            highlightSnippets(t);
            applyQueryToViewLinks();
    } else {
        // Нет результатов, но нужно обновить светофоры для отображения жёлтого цвета
        updateTrafficLightsAfterSearch();
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
        .then(safeFetchJson)
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

// --- Build Index auto (с единой шкалой прогресса и SSE) ---
function rebuildIndexWithProgress() {
    const bar = document.getElementById('indexBuildProgress');
    const fill = document.getElementById('indexBuildFill');
    const text = document.getElementById('indexBuildText');
    const processedCount = document.getElementById('indexProcessedCount');
    const totalCount = document.getElementById('indexTotalCount');
    const currentFileInfo = document.getElementById('currentFileInfo');
    
    if (bar) bar.style.display = 'flex';
    if (fill) {
        fill.style.width = '0%';
        fill.style.backgroundColor = '';  // Сброс цвета ошибки
    }
    if (text) text.textContent = 'Подготовка...';
    if (processedCount) processedCount.textContent = '0';
    if (totalCount) totalCount.textContent = '0';
    if (currentFileInfo) currentFileInfo.textContent = '';
    
    const startTime = Date.now();
    
    return new Promise((resolve, reject) => {
        // Запускаем индексацию
        fetch('/build_index', { method: 'POST' })
            .then(safeFetchJson)
            .then(data => {
                if (!data.success) {
                    throw new Error(data.message || 'Ошибка запуска индексации');
                }
                
                // Подключаемся к SSE endpoint для получения прогресса
                const eventSource = new EventSource('/build_index_progress');
                
                eventSource.onmessage = function(event) {
                    try {
                        const progress = JSON.parse(event.data);
                        
                        // Обновляем UI
                        if (progress.status === 'running') {
                            const percent = progress.total_files > 0 
                                ? Math.round((progress.processed_files / progress.total_files) * 100) 
                                : 0;
                            
                            if (fill) fill.style.width = percent + '%';
                            if (processedCount) processedCount.textContent = progress.processed_files;
                            if (totalCount) totalCount.textContent = progress.total_files;
                            if (text) text.textContent = `Обработка: ${progress.processed_files}/${progress.total_files}`;
                            if (currentFileInfo) currentFileInfo.textContent = progress.current_file || '';
                        } 
                        else if (progress.status === 'completed') {
                            // Завершено успешно
                            eventSource.close();
                            
                            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                            
                            if (fill) fill.style.width = '100%';
                            if (processedCount) processedCount.textContent = progress.processed_files;
                            if (totalCount) totalCount.textContent = progress.total_files;
                            if (text) text.textContent = `Готово: ${progress.processed_files} файлов за ${elapsed}с`;
                            if (currentFileInfo) currentFileInfo.textContent = '';
                            
                            refreshIndexStatus();
                            updateFilesList();
                            
                            setTimeout(() => { 
                                if (bar) bar.style.display = 'none'; 
                                if (fill) {
                                    fill.style.width = '0%';
                                    fill.style.backgroundColor = '';
                                }
                            }, 3000);
                            
                            resolve();
                        } 
                        else if (progress.status === 'error') {
                            // Ошибка
                            eventSource.close();
                            
                            if (fill) {
                                fill.style.width = '100%';
                                fill.style.backgroundColor = '#dc3545';
                            }
                            if (text) text.textContent = 'Ошибка: ' + (progress.error || 'Неизвестная ошибка');
                            if (currentFileInfo) currentFileInfo.textContent = '';
                            
                            showMessage('Ошибка построения индекса: ' + (progress.error || 'Неизвестная ошибка'));
                            
                            setTimeout(() => { 
                                if (bar) bar.style.display = 'none'; 
                                if (fill) {
                                    fill.style.width = '0%';
                                    fill.style.backgroundColor = '';
                                }
                            }, 3000);
                            
                            reject(new Error(progress.error || 'Ошибка индексации'));
                        }
                    } catch (err) {
                        console.error('Ошибка парсинга прогресса:', err);
                    }
                };
                
                eventSource.onerror = function(err) {
                    console.error('SSE ошибка:', err);
                    eventSource.close();
                    
                    // Если ошибка SSE, но индексация могла завершиться — проверим статус
                    refreshIndexStatus();
                    updateFilesList();
                    
                    if (fill) {
                        fill.style.width = '100%';
                        fill.style.backgroundColor = '#ffc107'; // Предупреждение
                    }
                    if (text) text.textContent = 'Соединение прервано, проверьте результат';
                    
                    setTimeout(() => { 
                        if (bar) bar.style.display = 'none'; 
                        if (fill) {
                            fill.style.width = '0%';
                            fill.style.backgroundColor = '';
                        }
                    }, 3000);
                    
                    resolve(); // Не блокируем, т.к. индексация могла завершиться
                };
            })
            .catch(err => {
                if (fill) {
                    fill.style.width = '100%';
                    fill.style.backgroundColor = '#dc3545';
                }
                if (text) text.textContent = 'Ошибка: ' + (err.message || 'Неизвестная ошибка');
                if (currentFileInfo) currentFileInfo.textContent = '';
                
                showMessage('Ошибка построения индекса: ' + (err.message || 'Неизвестная ошибка'));
                
                setTimeout(() => { 
                    if (bar) bar.style.display = 'none'; 
                    if (fill) {
                        fill.style.width = '0%';
                        fill.style.backgroundColor = '';
                    }
                }, 3000);
                
                reject(err);
            });
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
    // Первая инициализация списка файлов через API, чтобы отрисовать светофоры
    updateFilesList().then(() => {
        applyQueryToViewLinks();
        // Если поиск уже выполнялся ранее и результаты присутствуют в DOM, пересчитаем светофоры
        if (window.TrafficLights && window.TrafficLights.isSearchPerformed()) {
            updateTrafficLightsAfterSearch();
        }
    });
});

// --- Index status ---
function refreshIndexStatus() {
    if (!indexStatus) return;
    fetch('/index_status')
        .then(safeFetchJson)
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

// --- Analysis Module (increment-012) ---
const analyzeBtn = document.getElementById('analyzeBtn');
if (analyzeBtn) {
    analyzeBtn.addEventListener('click', async () => {
        try {
            // Проверяем наличие индекса
            const statusResp = await fetch('/analysis/status');
            const status = await statusResp.json();
            
            if (!status.index_exists) {
                showMessage('Сначала создайте индекс с помощью кнопки "Построить индекс"');
                return;
            }
            
            // Показываем прогресс
            analyzeBtn.disabled = true;
            analyzeBtn.innerHTML = '<i class="icon">⏳</i> Анализ выполняется...';
            
            // Запускаем анализ
            const resp = await fetch('/analysis/run', { method: 'POST' });
            const data = await resp.json();
            
            if (data.success) {
                // Открываем модальное окно для редактирования результатов
                showAnalysisEditor(data.data);
            } else {
                showMessage('Ошибка анализа: ' + data.message);
            }
        } catch (error) {
            console.error('Ошибка анализа:', error);
            showMessage('Ошибка при выполнении анализа');
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = '<i class="icon">📊</i> Анализ документов';
        }
    });
}

function showAnalysisEditor(analysisData) {
    // Создаём модальное окно для редактирования результатов
    const modal = document.createElement('div');
    modal.className = 'analysis-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    `;
    
    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
        background: white;
        padding: 30px;
        border-radius: 8px;
        max-width: 800px;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    `;
    
    const procurement = analysisData.procurement || {};
    
    modalContent.innerHTML = `
        <h2 style="margin-top: 0; color: #2c3e50;">Результаты анализа</h2>
        <p style="color: #7f8c8d;">Проверьте и при необходимости отредактируйте извлечённые данные</p>
        
        <div style="margin: 20px 0;">
            <h3 style="color: #34495e;">Основная информация</h3>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">Наименование:</label>
                <input type="text" id="edit_title" value="${escapeHtml(procurement.title || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">Номер закупки:</label>
                <input type="text" id="edit_number" value="${escapeHtml(procurement.number || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">ИКЗ:</label>
                <input type="text" id="edit_ikz" value="${escapeHtml(procurement.ikz || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
        </div>
        
        <div style="margin: 20px 0;">
            <h3 style="color: #34495e;">Цены</h3>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">Начальная цена:</label>
                <input type="text" id="edit_initial_price" value="${escapeHtml(procurement.initial_price || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
        </div>
        
        <div style="margin: 20px 0;">
            <h3 style="color: #34495e;">Заказчик</h3>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">Наименование:</label>
                <input type="text" id="edit_customer_name" value="${escapeHtml(procurement.customer?.name || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            <div style="margin: 10px 0;">
                <label style="display: block; font-weight: bold; margin-bottom: 5px;">ИНН:</label>
                <input type="text" id="edit_customer_inn" value="${escapeHtml(procurement.customer?.inn || '')}" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
        </div>
        
        <div style="margin-top: 30px; display: flex; gap: 10px; justify-content: flex-end;">
            <button id="cancelAnalysisBtn" class="btn btn-secondary" style="padding: 10px 20px;">Отмена</button>
            <button id="saveAnalysisBtn" class="btn btn-primary" style="padding: 10px 20px;">Сохранить и открыть отчёт</button>
        </div>
    `;
    
    modal.appendChild(modalContent);
    document.body.appendChild(modal);
    
    // Обработчик закрытия
    document.getElementById('cancelAnalysisBtn').addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Обработчик сохранения
    document.getElementById('saveAnalysisBtn').addEventListener('click', async () => {
        // Собираем отредактированные данные
        const editedData = JSON.parse(JSON.stringify(analysisData));
        editedData.procurement.title = document.getElementById('edit_title').value;
        editedData.procurement.number = document.getElementById('edit_number').value;
        editedData.procurement.ikz = document.getElementById('edit_ikz').value;
        editedData.procurement.initial_price = document.getElementById('edit_initial_price').value;
        
        if (!editedData.procurement.customer) {
            editedData.procurement.customer = {};
        }
        editedData.procurement.customer.name = document.getElementById('edit_customer_name').value;
        editedData.procurement.customer.inn = document.getElementById('edit_customer_inn').value;
        
        try {
            // Отправляем на сохранение
            const saveBtn = document.getElementById('saveAnalysisBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Сохранение...';
            
            const resp = await fetch('/analysis/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: editedData })
            });
            
            const result = await resp.json();
            
            if (result.success) {
                // Открываем отчёт в новой вкладке
                window.open(result.report_url, '_blank');
                document.body.removeChild(modal);
                showMessage('Анализ сохранён, отчёт открыт в новой вкладке');
            } else {
                showMessage('Ошибка сохранения: ' + result.message);
                saveBtn.disabled = false;
                saveBtn.textContent = 'Сохранить и открыть отчёт';
            }
        } catch (error) {
            console.error('Ошибка сохранения:', error);
            showMessage('Ошибка при сохранении результатов');
        }
    });
}
