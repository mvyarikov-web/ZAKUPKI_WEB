/**
 * Утилиты для работы с авторизацией пользователя
 */

// Получить токен из localStorage
function getAuthToken() {
    return localStorage.getItem('auth_token');
}

// Сохранить токен в localStorage
function setAuthToken(token) {
    localStorage.setItem('auth_token', token);
}

// Удалить токен из localStorage
function removeAuthToken() {
    localStorage.removeItem('auth_token');
}

// Получить информацию о текущем пользователе
async function getCurrentUser() {
    const token = getAuthToken();
    if (!token) {
        return null;
    }
    
    try {
        const response = await fetch('/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            return await response.json();
        } else {
            // Токен невалиден
            removeAuthToken();
            return null;
        }
    } catch (error) {
        console.error('Ошибка получения информации о пользователе:', error);
        return null;
    }
}

// Выход из системы
async function logout() {
    const token = getAuthToken();
    if (token) {
        try {
            await fetch('/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
        } catch (error) {
            console.error('Ошибка выхода:', error);
        }
    }
    
    removeAuthToken();
    window.location.href = '/auth/login_page';
}

// Отобразить панель пользователя
async function renderUserPanel() {
    const user = await getCurrentUser();
    
    if (!user) {
        // Если пользователь не авторизован и это не страница логина, перенаправляем
        const currentPath = window.location.pathname;
        const isLoginPage = currentPath.includes('/auth/login_page') || currentPath === '/auth/login_page';
        const isAuthRoute = currentPath.startsWith('/auth/');
        
        if (!isLoginPage && !isAuthRoute) {
            // Небольшая задержка перед редиректом для завершения других операций
            setTimeout(() => {
                window.location.href = '/auth/login_page';
            }, 100);
        }
        return;
    }
    
    // Создаём панель пользователя
    const userPanel = document.createElement('div');
    userPanel.className = 'user-panel';
    userPanel.innerHTML = `
        <span class="user-icon">👤</span>
        <div class="user-info">
            <span class="user-label">Пользователь</span>
            <span class="user-email">${user.email}</span>
        </div>
        <button class="logout-btn" onclick="logout()">
            🚪 Выход
        </button>
    `;
    
    document.body.appendChild(userPanel);
}

// Добавить токен ко всем fetch-запросам
const originalFetch = window.fetch;
window.fetch = function(...args) {
    const token = getAuthToken();
    if (token) {
        if (args[1]) {
            args[1].headers = args[1].headers || {};
            if (args[1].headers instanceof Headers) {
                args[1].headers.set('Authorization', `Bearer ${token}`);
            } else {
                args[1].headers['Authorization'] = `Bearer ${token}`;
            }
        } else {
            args[1] = { headers: { 'Authorization': `Bearer ${token}` } };
        }
    }
    return originalFetch.apply(this, args);
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Отображаем панель пользователя на всех страницах кроме логина
    if (!window.location.pathname.includes('/auth/login_page')) {
        renderUserPanel();
    }
});
