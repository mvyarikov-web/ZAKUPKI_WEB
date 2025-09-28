// --- Drag & Drop ---
const fileInput = document.getElementById('fileInput');
const selectFilesBtn = document.getElementById('selectFilesBtn');
const selectFolderBtn = document.getElementById('selectFolderBtn');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const filesList = document.getElementById('filesList');
const fileCount = document.getElementById('fileCount');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const buildIndexBtn = document.getElementById('buildIndexBtn');
const clearResultsBtn = document.getElementById('clearResultsBtn');
const searchResults = document.getElementById('searchResults');
const messageModal = document.getElementById('messageModal');
const modalMessage = document.getElementById('modalMessage');
const closeModal = document.querySelector('.close');
const indexStatus = document.getElementById('indexStatus');

// --- File Select ---
selectFilesBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFiles);

// --- Folder Select (experimental, works in Chromium browsers) ---
selectFolderBtn.addEventListener('click', () => {
    const folderInput = document.createElement('input');
    folderInput.type = 'file';
    folderInput.webkitdirectory = true;
    folderInput.multiple = true;
    folderInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt';
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
    uploadProgress.style.display = 'flex';
    let uploaded = 0;
    progressFill.style.width = '0%';
    progressText.textContent = '0%';

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
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
            showMessage('Файлы успешно загружены!');
            updateFilesList();
        } else {
            showMessage(data.error || 'Ошибка загрузки файлов');
        }
        uploadProgress.style.display = 'none';
    })
    .catch((err) => {
        showMessage(err && err.message ? err.message : 'Ошибка загрузки файлов');
        uploadProgress.style.display = 'none';
    });
}

// --- Update Files List ---
function updateFilesList() {
    fetch('/')
        .then(res => res.text())
        .then(html => {
            // Парсим HTML и обновляем список файлов
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newFilesList = doc.getElementById('filesList');
            const newFileCount = doc.getElementById('fileCount');
            if (newFilesList && filesList) {
                filesList.innerHTML = newFilesList.innerHTML;
                // Восстанавливаем состояния папок после обновления
                setTimeout(restoreFolderStates, 100);
            }
            if (newFileCount && fileCount) fileCount.textContent = newFileCount.textContent;
        });
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
            showMessage('Файл удалён');
            updateFilesList();
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
            showMessage(data.message || 'Папка удалена успешно');
            updateFilesList();
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
searchBtn.addEventListener('click', () => {
    const terms = searchInput.value.trim();
    if (!terms) {
        showMessage('Введите ключевые слова для поиска');
        return;
    }
    searchResults.style.display = 'block';
    searchResults.innerHTML = '<div>Поиск...</div>';
    
    // Обновляем статусы файлов на "обрабатывается"
    const fileItems = document.querySelectorAll('.file-item');
    fileItems.forEach(item => {
        const statusIndicator = item.querySelector('.status-indicator');
        const statusText = item.querySelector('.status-text');
        if (statusIndicator && statusText) {
            statusIndicator.className = 'status-indicator status-processing';
            statusText.textContent = 'Обработка...';
        }
    });
    
    fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_terms: terms })
    })
    .then(res => res.json())
    .then(data => {
        if (data.results && data.results.length > 0) {
            searchResults.innerHTML = '';
            data.results.forEach(result => {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                const linkTarget = result.path ? `/result/${encodeURIComponent(result.path)}` : '#';
                item.innerHTML = `
                    <div class="result-header">
                        <span class="result-filename" title="Источник: ${result.source || ''}">${result.filename}</span>
                        <div class="found-terms">
                            ${result.found_terms.map(term => `<span class="found-term">${term}</span>`).join(' ')}
                        </div>
                        ${result.path ? `<a class="result-link" href="${linkTarget}" target="_blank">Страница результата</a>` : '<span class="result-link disabled" title="Файл из архива, нет прямой страницы результата">Виртуальный источник</span>'}
                    </div>
                    <div class="context-snippets">
                        ${result.context.map(snippet => `<div class="context-snippet" data-search-terms="${terms}">${snippet}</div>`).join('')}
                    </div>
                `;
                searchResults.appendChild(item);
            });
            // Подсветка ключевых слов в сниппетах результатов
            const snippets = searchResults.querySelectorAll('.context-snippet');
            const termsList = terms.split(',').map(t => t.trim()).filter(Boolean);
            snippets.forEach(sn => {
                let html = sn.innerHTML;
                termsList.forEach(term => {
                    const rx = new RegExp(`(${term.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')})`, 'gi');
                    html = html.replace(rx, '<span class="highlight">$1</span>');
                });
                sn.innerHTML = html;
            });
        } else {
            searchResults.innerHTML = '<div>Ничего не найдено по этим ключевым словам.</div>';
        }
        
        // Обновляем список файлов со статусами
        updateFilesList();
    })
    .catch(() => {
        searchResults.innerHTML = '<div>Ошибка поиска.</div>';
        updateFilesList();
    });
});

// --- Clear Results ---
clearResultsBtn.addEventListener('click', () => {
    if (!confirm('Вы уверены, что хотите очистить все результаты поиска? Эта операция необратима.')) {
        return;
    }
    
    fetch('/clear_results', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showMessage('Результаты поиска очищены');
            searchInput.value = '';
            searchResults.style.display = 'none';
            updateFilesList();
        } else {
            showMessage(data.message || 'Ошибка очистки результатов');
        }
    })
    .catch(() => {
        showMessage('Ошибка очистки результатов');
    });
});

// --- Build Index ---
if (buildIndexBtn) {
    buildIndexBtn.addEventListener('click', () => {
        buildIndexBtn.disabled = true;
        fetch('/build_index', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Индекс создан: ${data.index_path}\nРазмер: ${data.size} байт`);
                    refreshIndexStatus();
                } else {
                    showMessage(data.message || 'Ошибка построения индекса');
                }
            })
            .catch(() => showMessage('Ошибка построения индекса'))
            .finally(() => { buildIndexBtn.disabled = false; });
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
    restoreFolderStates();
    refreshIndexStatus();
    // периодический автопул статуса индекса
    setInterval(refreshIndexStatus, 8000);
});

// Для обратной совместимости
updateFilesList();
restoreFolderStates();

// --- Index status ---
function refreshIndexStatus() {
    if (!indexStatus) return;
    fetch('/index_status')
        .then(res => res.json())
        .then(data => {
            if (!data.exists) {
                indexStatus.textContent = 'Индекс: отсутствует';
                indexStatus.style.color = '#a00';
            } else {
                const size = (data.size || 0);
                const sizeKb = (size / 1024).toFixed(1);
                const entries = (data.entries == null) ? '—' : data.entries;
                indexStatus.textContent = `Индекс: есть, ${sizeKb} KB, записей: ${entries}`;
                indexStatus.style.color = '#2a2';
            }
        })
        .catch(() => {
            indexStatus.textContent = 'Индекс: ошибка запроса';
            indexStatus.style.color = '#a00';
        });
}
