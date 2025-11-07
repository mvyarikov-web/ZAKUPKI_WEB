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
const indexStatus = document.getElementById('indexStatus');

// --- Folder Select ---
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

// --- Files Select ---
selectFilesBtn.addEventListener('click', () => {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.multiple = true;
    // НЕ устанавливаем webkitdirectory, чтобы работал обычный выбор файлов
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
                const displayPath = (fullPath ? fullPath + '/' : '') + folderPath;
                if (selectedFolderPathEl) selectedFolderPathEl.textContent = displayPath;
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

    const userId = window.APP_USER_ID || localStorage.getItem('app_user_id') || '';
    fetch('/upload', {
        method: 'POST',
        headers: userId ? { 'X-User-ID': userId } : {},
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
        MessageManager.error(err && err.message ? err.message : 'Ошибка загрузки файлов');
        uploadProgress.style.display = 'none';
    });
}



// --- Render Tree (Recursive) ---
function renderTreeNode(folderName, treeNode, file_statuses, folderStates, depth = 0) {
    const { folders = {}, files = [] } = treeNode;
    const folderId = `folder-${folderName}-${depth}`;
    const isExpanded = folderStates[folderId] !== false; // По умолчанию развёрнуты
    
    const folderDiv = document.createElement('div');
    folderDiv.className = 'folder-container';
    folderDiv.id = folderId;
    folderDiv.style.marginLeft = `${depth * 20}px`; // Отступ для вложенности
    
    const headerDiv = document.createElement('div');
    headerDiv.className = 'folder-header';
    headerDiv.onclick = () => toggleFolder(folderId.replace('folder-', ''));
    
    // Подсчитываем общее количество файлов в папке и подпапках
    const totalFiles = files.length + Object.values(folders).reduce((sum, subfolder) => {
        return sum + countFilesInTree(subfolder);
    }, 0);
    
    headerDiv.innerHTML = `
        <input type="checkbox" class="folder-checkbox" title="Выбрать все файлы в папке" style="margin-right:8px;">
        <span class="folder-icon">📁</span>
        <span class="folder-name">${escapeHtml(folderName)}</span>
        <span class="file-count-badge">${totalFiles}</span>
        <span class="toggle-icon">${isExpanded ? '▼' : '▶'}</span>
    `;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'folder-content';
    contentDiv.style.display = isExpanded ? 'block' : 'none';
    
    // Добавляем файлы текущей папки
    files.forEach(file => {
        const fileDiv = renderFileItem(file, file_statuses);
        contentDiv.appendChild(fileDiv);
    });
    
    // Рекурсивно добавляем подпапки
    Object.keys(folders).sort().forEach(subfolderName => {
        const subfolderNode = folders[subfolderName];
        const subfolderDiv = renderTreeNode(subfolderName, subfolderNode, file_statuses, folderStates, depth + 1);
        contentDiv.appendChild(subfolderDiv);
    });
    
    // Обработчик для чекбокса папки: выбрать/снять все в папке (включая вложенные папки)
    const folderCheckbox = headerDiv.querySelector('.folder-checkbox');
    if (folderCheckbox) {
        folderCheckbox.addEventListener('click', (ev) => ev.stopPropagation());
        folderCheckbox.addEventListener('change', (ev) => {
            const checked = ev.target.checked;
            // Выбираем все файлы
            const fileCbs = contentDiv.querySelectorAll('.file-checkbox');
            fileCbs.forEach(cb => { cb.checked = checked; });
            // Выбираем все вложенные папки (рекурсивно)
            const folderCbs = contentDiv.querySelectorAll('.folder-checkbox');
            folderCbs.forEach(cb => { cb.checked = checked; });
            
            // Если снимаем галку, проверяем родительскую папку
            if (!checked) {
                updateParentCheckbox(folderDiv);
            }
        });
    }
    
    folderDiv.appendChild(headerDiv);
    folderDiv.appendChild(contentDiv);
    return folderDiv;
}

// Функция для обновления галки родительской папки
function updateParentCheckbox(folderElement) {
    // Ищем родительский folder-container
    const parentContent = folderElement.parentElement;
    if (!parentContent || !parentContent.classList.contains('folder-content')) {
        return; // Нет родителя или достигли корня
    }
    
    const parentFolder = parentContent.parentElement;
    if (!parentFolder || !parentFolder.classList.contains('folder-container')) {
        return;
    }
    
    // Ищем чекбокс родительской папки
    const parentCheckbox = parentFolder.querySelector(':scope > .folder-header > .folder-checkbox');
    if (!parentCheckbox) {
        return;
    }
    
    // Проверяем, есть ли хотя бы один отмеченный элемент в родительской папке
    const checkedFiles = parentContent.querySelectorAll('.file-checkbox:checked');
    const checkedFolders = parentContent.querySelectorAll('.folder-checkbox:checked');
    
    const hasCheckedItems = checkedFiles.length > 0 || checkedFolders.length > 0;
    
    // Если нет отмеченных элементов, снимаем галку с родителя
    if (!hasCheckedItems && parentCheckbox.checked) {
        parentCheckbox.checked = false;
        // Рекурсивно проверяем родителя родителя
        updateParentCheckbox(parentFolder);
    }
}

function countFilesInTree(treeNode) {
    const { folders = {}, files = [] } = treeNode;
    return files.length + Object.values(folders).reduce((sum, subfolder) => {
        return sum + countFilesInTree(subfolder);
    }, 0);
}

// --- Update Files List ---
function updateFilesList() {
    return fetch('/files_json')
        .then(res => res.json())
        .then(data => {
            const { tree = {folders: {}, files: []}, file_statuses = {} } = data;
            
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
            
            // Отображаем корневые файлы (если есть)
            if (tree.files && tree.files.length > 0) {
                const rootDiv = renderTreeNode('Загруженные файлы', {files: tree.files, folders: {}}, file_statuses, folderStates, 0);
                filesList.appendChild(rootDiv);
            }
            
            // Отображаем папки верхнего уровня
            Object.keys(tree.folders).sort().forEach(folderName => {
                const folderNode = tree.folders[folderName];
                const folderDiv = renderTreeNode(folderName, folderNode, file_statuses, folderStates, 0);
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
        // Добавляем токен в URL для авторизации (используем auth.js:getAuthToken)
        const token = (typeof getAuthToken === 'function') ? getAuthToken() : (localStorage.getItem('auth_token') || localStorage.getItem('authToken'));
        const viewUrl = token ?
            `/view/${encodeURIComponent(file.path)}?token=${encodeURIComponent(token)}` :
            `/view/${encodeURIComponent(file.path)}`;
        fileLink = `<a class="file-name result-file-link" href="${viewUrl}" target="_blank" rel="noopener">${escapeHtml(file.name)}</a>`;
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
    
    // Чекбокс показываем только если файл проиндексирован (char_count > 0)
    const showCheckbox = !(charCount === 0);
    const checkboxHtml = showCheckbox
        ? `<input type="checkbox" class="file-checkbox" data-file-path="${escapeHtml(file.path)}" style="margin-right:8px;">`
        : '';
    fileDiv.innerHTML = `
        <div class="file-info">
            ${checkboxHtml}
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
    
    // Добавляем обработчик для чекбокса файла
    const fileCheckbox = fileDiv.querySelector('.file-checkbox');
    if (fileCheckbox) {
        fileCheckbox.addEventListener('change', (ev) => {
            // Если снимаем галку, проверяем родительскую папку
            if (!ev.target.checked) {
                // Ищем родительский folder-content
                const parentContent = wrapper.closest('.folder-content');
                if (parentContent) {
                    const parentFolder = parentContent.parentElement;
                    if (parentFolder && parentFolder.classList.contains('folder-container')) {
                        updateParentCheckbox(parentFolder);
                    }
                }
            }
        });
    }
    
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
    
    const userId = window.APP_USER_ID || localStorage.getItem('app_user_id') || '';
    const resp = await fetch('/search', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, userId ? { 'X-User-ID': userId } : {}),
        body: JSON.stringify({ search_terms: terms })
    });
    const data = await resp.json();
    try { localStorage.setItem('last_search_terms', terms); } catch (e) {}
    // Критично: сначала обновляем список файлов и дожидаемся рендера, чтобы не потерять результаты
    await updateFilesList();
    
    if (data.results && data.results.length > 0) {
        // Подсчитываем количество совпадений и наличие сниппетов
        const totalMatches = data.results.reduce((sum, r) => {
            if (r.per_term) {
                return sum + r.per_term.reduce((termSum, t) => termSum + (t.count || 0), 0);
            }
            return sum;
        }, 0);
        const snippetCount = data.results.reduce((sum, r) => {
            if (r.per_term) {
                return sum + r.per_term.reduce((s, t) => s + ((t.snippets || []).length), 0);
            }
            return sum;
        }, 0);
        const totalDocs = data.results.length;
        
        // Баннер выводим только если есть совпадения И есть сниппеты
        if (totalMatches > 0 && snippetCount > 0 && typeof MessageManager !== 'undefined') {
            MessageManager.success(
                `✅ Найдено ${totalMatches} совпадений в ${totalDocs} документах`,
                'main'
            );
        }
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
                        const snippetsBlock = snips ? `<div class="context-snippets">${snips}</div>` : '';
                        return `<div class="per-term-block">
                            <div class="found-terms"><span class="found-term">${termHtml}</span></div>
                            ${snippetsBlock}
                        </div>`;
                    }).join('');
                    
                    resultsContainer.innerHTML = perTermHtml;
                    resultsContainer.style.display = 'block';
                    fileWrapper.setAttribute('data-has-results', '1');
                }
            }
        });
        
        // Сортировка: файлы с результатами наверх
        document.querySelectorAll('.folder-content').forEach(contentDiv => {
            const wrappers = Array.from(contentDiv.querySelectorAll(':scope > .file-item-wrapper'));
            const scored = wrappers.map(el => {
                // Файлы с результатами получают высокий приоритет
                const hasResults = el.hasAttribute('data-has-results');
                const score = hasResults ? 1 : 0;
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
        // Нет результатов — ничего не показываем в шапке
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
        if (!confirm('Удалить ВСЕ загруженные файлы и папки. Это действие необратимо!')) {
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
                
                // Сбрасываем прогресс-бары
                const uploadBar = document.getElementById('uploadProgress');
                const uploadFill = document.getElementById('progressFill');
                const uploadText = document.getElementById('progressText');
                const indexBar = document.getElementById('indexBuildProgress');
                const indexFill = document.getElementById('indexBuildFill');
                const indexText = document.getElementById('indexBuildText');
                const indexTime = document.getElementById('indexBuildTime');
                
                if (uploadBar) uploadBar.style.display = 'none';
                if (uploadFill) uploadFill.style.width = '0%';
                if (uploadText) uploadText.textContent = '0%';
                if (indexBar) indexBar.style.display = 'none';
                if (indexFill) {
                    indexFill.style.width = '0%';
                    indexFill.classList.remove('completed');
                }
                if (indexText) indexText.textContent = 'Построение индекса…';
                
                // Полный сброс таймера индексации
                resetIndexingTimer();
                
                // Обновляем список файлов (покажет пустое дерево)
                updateFilesList();
                refreshIndexStatus();
                
                // Сообщение об успехе убрано - только тихое обновление UI
                // Показываем ошибки, если они есть
                if (data.errors && data.errors.length > 0) {
                    const errorList = data.errors.map(e => `  - ${e.path}: ${e.error}`).join('\n');
                    MessageManager.warning(`При удалении возникли ошибки:\n${errorList}`, 'main');
                }
            } else {
                MessageManager.error('Ошибка при очистке: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Ошибка при очистке:', error);
            MessageManager.error('Ошибка при очистке данных');
        });
    });
}

// (Кнопка очистки результатов удалена — очистка выполняется при пустом поисковом запросе)

// --- Build Index auto ---
// Глобальная переменная для таймера индексации
let indexingTimerInterval = null;
let indexingStartTime = null;
let accumulatedIndexingTime = 0; // Накопленное время в секундах

function formatElapsedTime(seconds) {
    if (seconds < 60) {
        return `${seconds} сек`;
    }
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins} мин ${secs} сек`;
}

function startIndexingTimer() {
    const timeDisplay = document.getElementById('indexBuildTime');
    if (!timeDisplay) return;
    
    // Останавливаем предыдущий таймер если он был запущен
    if (indexingTimerInterval) {
        clearInterval(indexingTimerInterval);
        indexingTimerInterval = null;
    }
    
    // Запоминаем время начала новой индексации
    indexingStartTime = Date.now();
    
    // Обновляем таймер каждую секунду
    indexingTimerInterval = setInterval(() => {
        const currentSessionTime = Math.floor((Date.now() - indexingStartTime) / 1000);
        const totalTime = accumulatedIndexingTime + currentSessionTime;
        timeDisplay.textContent = formatElapsedTime(totalTime);
    }, 1000);
}

function stopIndexingTimer(keepDisplay = true) {
    if (indexingTimerInterval) {
        // Добавляем время текущей сессии к накопленному
        if (indexingStartTime) {
            const currentSessionTime = Math.floor((Date.now() - indexingStartTime) / 1000);
            accumulatedIndexingTime += currentSessionTime;
            indexingStartTime = null;
        }
        
        clearInterval(indexingTimerInterval);
        indexingTimerInterval = null;
    }
    
    if (keepDisplay) {
        const timeDisplay = document.getElementById('indexBuildTime');
        if (timeDisplay) {
            timeDisplay.textContent = formatElapsedTime(accumulatedIndexingTime);
        }
    }
}

function resetIndexingTimer() {
    // Полный сброс таймера (вызывается при "Удалить все")
    if (indexingTimerInterval) {
        clearInterval(indexingTimerInterval);
        indexingTimerInterval = null;
    }
    indexingStartTime = null;
    accumulatedIndexingTime = 0;
    
    const timeDisplay = document.getElementById('indexBuildTime');
    if (timeDisplay) {
        timeDisplay.textContent = '';
    }
}

function rebuildIndexWithProgress() {
    const bar = document.getElementById('indexBuildProgress');
    const fill = document.getElementById('indexBuildFill');
    const text = document.getElementById('indexBuildText');
    const timeDisplay = document.getElementById('indexBuildTime');
    
    // Показываем прогресс-бар
    if (bar) {
        bar.style.display = 'block';
        bar.style.visibility = 'visible';
    }
    
    // Устанавливаем начальное состояние
    if (fill) {
        fill.style.width = '10%';
        fill.classList.remove('completed');
    }
    
    if (text) text.textContent = 'Построение индекса…';
    if (timeDisplay) timeDisplay.textContent = '0 сек';
    
    // Запускаем таймер
    startIndexingTimer();
    
    // Запускаем построение индекса с групповой индексацией
    const userId = window.APP_USER_ID || localStorage.getItem('app_user_id') || '';
    return fetch('/build_index', { 
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, userId ? { 'X-User-ID': userId } : {}),
        body: JSON.stringify({ use_groups: true })
    })
        .then(res => res.json())
        .then(data => {
            if (!data.success) throw new Error(data.message || 'Ошибка построения индекса');
            
            // Запускаем опрос статуса групп
            return pollIndexGroupStatus(fill, text);
        })
        .catch(error => {
            stopIndexingTimer(false);
            throw error;
        })
        .finally(() => {
            // Останавливаем таймер, но оставляем финальное время на экране
            stopIndexingTimer(true);
            // Не скрываем прогресс после завершения — оставляем 100% и статус
        });
}

// --- Poll Index Group Status (increment-014) ---
function pollIndexGroupStatus(fill, text) {
    return new Promise((resolve, reject) => {
        const maxAttempts = 120; // 120 секунд максимум (2 минуты)
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
                        statusText = '✅ Быстрые файлы готовы';
                    }
                    if (groupStatus.medium === 'completed') {
                        progress = 66;
                        statusText = '✅ Средние файлы готовы';
                    }
                    if (groupStatus.slow === 'completed' || status === 'completed') {
                        progress = 100;
                        statusText = '✅ Все файлы обработаны';
                    }
                    
                    // Добавляем индикацию текущей группы, если индексация идёт
                    if (status === 'running' && currentGroup) {
                        const groupLabels = {
                            'fast': '🔄 Обработка быстрых файлов',
                            'medium': '🔄 Обработка средних файлов',
                            'slow': '🔄 Обработка медленных файлов'
                        };
                        statusText = groupLabels[currentGroup] || statusText;
                    }
                    
                    // Плавное заполнение полоски с CSS transition
                    if (fill) {
                        fill.style.transition = 'width 0.5s ease-out';
                        fill.style.width = progress + '%';
                        
                        // Убираем анимацию "бегущих полосок" когда завершено
                        if (status === 'completed' || progress === 100) {
                            fill.classList.add('completed');
                        } else {
                            fill.classList.remove('completed');
                        }
                    }
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

// --- Старая функция showMessage удалена, используется MessageManager ---
// Обратная совместимость через message-manager.js: window.showMessage

// Функция получения выбранных файлов (используется в rag-analysis.js)
function getSelectedFiles() {
    const checkboxes = document.querySelectorAll('.file-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.dataset.filePath);
}
window.getSelectedFiles = getSelectedFiles;

// --- Folder Toggle ---
function toggleFolder(folderName) {
    const folderId = 'folder-' + folderName;
    const folderElement = document.getElementById(folderId);
    const folderContainer = folderElement.closest('.folder-container');
    
    if (folderContainer.classList.contains('collapsed')) {
        folderContainer.classList.remove('collapsed');
        // Сохраняем состояние в localStorage
        localStorage.setItem('folder-' + folderName, 'expanded');
        
        // Сохраняем последнюю открытую папку на сервере
        saveLastFolder(folderName);
    } else {
        folderContainer.classList.add('collapsed');
        // Сохраняем состояние в localStorage
        localStorage.setItem('folder-' + folderName, 'collapsed');
    }
}

// Сохранить последнюю открытую папку на сервере
async function saveLastFolder(folderPath) {
    try {
        const token = localStorage.getItem('authToken');
        if (!token) return; // Пропускаем, если нет токена
        
        const response = await fetch('/auth/save-last-folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ folder_path: folderPath })
        });
        
        if (!response.ok) {
            console.warn('Failed to save last folder:', await response.text());
        }
    } catch (error) {
        console.error('Error saving last folder:', error);
    }
}

// --- Restore Folder States ---
async function restoreFolderStates() {
    // Сначала загружаем last_folder с сервера
    let lastFolderFromServer = null;
    try {
        const token = localStorage.getItem('authToken');
        if (token) {
            const response = await fetch('/auth/get-last-folder', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.folder_path) {
                    lastFolderFromServer = data.folder_path;
                }
            }
        }
    } catch (error) {
        console.error('Error loading last folder:', error);
    }
    
    const folderContainers = document.querySelectorAll('.folder-container');
    folderContainers.forEach(container => {
        const folderHeader = container.querySelector('.folder-header');
        if (folderHeader) {
            const folderName = folderHeader.querySelector('.folder-name').textContent;
            
            // Если это последняя открытая папка с сервера - раскрываем её
            if (lastFolderFromServer && folderName === lastFolderFromServer) {
                container.classList.remove('collapsed');
                localStorage.setItem('folder-' + folderName, 'expanded');
            } else {
                // Иначе восстанавливаем из localStorage
                const savedState = localStorage.getItem('folder-' + folderName);
                
                if (savedState === 'collapsed') {
                    container.classList.add('collapsed');
                } else {
                    container.classList.remove('collapsed');
                }
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
            
            // Проверяем статус индексации
            const currentStatus = data.status || 'idle';
            const dbInfo = data.db || {};
            const docs = (typeof dbInfo.documents === 'number') ? dbInfo.documents : null;
            const lastIdxStr = dbInfo.last_indexed_at ? (() => {
                try { return new Date(dbInfo.last_indexed_at).toLocaleString('ru-RU'); } catch (_) { return null; }
            })() : null;
            const dbSuffix = (docs !== null || lastIdxStr)
                ? ' | ' + [
                    (docs !== null ? `БД документов: ${docs}` : null),
                    (lastIdxStr ? `обновлён: ${lastIdxStr}` : null)
                  ].filter(Boolean).join(', ')
                : '';
            
            if (!data.exists) {
                indexStatus.textContent = 'Индекс (БД): не создан' + dbSuffix;
                indexStatus.style.color = '#a00';
            } else {
                const entries = (data.entries == null) ? '—' : data.entries;
                if (currentStatus === 'completed' || currentStatus === 'idle') {
                    indexStatus.textContent = `Индекс (БД): готов, документов: ${entries}` + dbSuffix;
                    indexStatus.style.color = '#2a2';
                } else if (currentStatus === 'running') {
                    indexStatus.textContent = `Индекс (БД): обновляется…` + dbSuffix;
                    indexStatus.style.color = '#f90';
                } else {
                    indexStatus.textContent = `Индекс (БД): готов, документов: ${entries}` + dbSuffix;
                    indexStatus.style.color = '#2a2';
                }
            }
            
            // Обновляем индикатор групп (increment-014)
            if (data.group_status) {
                updateGroupsIndicator(data.group_status, currentStatus);
            }
        })
        .catch(() => {
            indexStatus.textContent = 'Индекс (БД): ошибка запроса';
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
            // Проставляем токен авторизации в query, если он есть
            try {
                const token = (typeof getAuthToken === 'function') ? getAuthToken() : (localStorage.getItem('auth_token') || localStorage.getItem('authToken'));
                if (token) {
                    url.searchParams.set('token', token);
                }
            } catch (_) {}
            if (terms.length > 0) {
                url.searchParams.set('q', terms.join(','));
            } else {
                url.searchParams.delete('q');
            }
            a.setAttribute('href', url.pathname + (url.search ? url.search : ''));
        } catch (_) {}
    });
}
