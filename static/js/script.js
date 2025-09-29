// --- Drag & Drop ---
// Отключаем выбор одиночных файлов — только папки
const selectFolderBtn = document.getElementById('selectFolderBtn');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const filesList = document.getElementById('filesList');
const fileCount = document.getElementById('fileCount');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
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
    const allowedExt = new Set(['pdf','doc','docx','xls','xlsx','txt']);
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
            showMessage('Файл удалён. Перестраиваем индекс…');
            return rebuildIndexWithProgress().then(() => {
                showMessage('Индекс перестроен');
                updateFilesList();
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
    // Перед поиском — гарантируем, что индекс свежий
    searchResults.style.display = 'block';
    searchResults.innerHTML = '<div>Обновляем индекс...</div>';
    rebuildIndexWithProgress()
    .then(() => {
        searchResults.innerHTML = '<div>Поиск...</div>';
        return fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_terms: terms })
        });
    })
    .then(res => res.json())
    .then(data => {
        if (data.results && data.results.length > 0) {
            searchResults.innerHTML = '';
            const terms = termsFromInput();
            data.results.forEach(result => {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                const snippetsHtml = (result.context || []).slice(0, 3).map(s => `<div class="context-snippet">${escapeHtml(s)}</div>`).join('');
                item.innerHTML = `
                    <div class="result-header">
                        <span class="result-filename" title="Источник: ${result.source || ''}">${result.filename}</span>
                        <div class="found-terms">
                            ${result.found_terms.map(term => `<span class="found-term">${term}</span>`).join(' ')}
                        </div>
                    </div>
                    <div class="context-snippets">${snippetsHtml || '<div class="context-empty">Нет сниппетов</div>'}</div>
                `;
                searchResults.appendChild(item);
            });
            // Подсветка терминов в сниппетах
            highlightSnippets(terms);
        } else {
            searchResults.innerHTML = '<div>Ничего не найдено по этим ключевым словам.</div>';
        }
    })
    .catch(() => {
        searchResults.innerHTML = '<div>Ошибка поиска.</div>';
    });
});

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
    return searchInput.value.split(',').map(t => t.trim()).filter(Boolean);
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
});

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
