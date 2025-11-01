/**
 * Централизованный модуль управления сообщениями
 * Показывает сообщения в специальных областях на главном экране и в модальных окнах
 */
(function() {
    'use strict';

    // Типы сообщений
    const MessageType = {
        INFO: 'info',
        SUCCESS: 'success',
        WARNING: 'warning',
        ERROR: 'error'
    };

    // Контексты отображения
    const Context = {
        MAIN: 'main',        // Главный экран
        MODAL: 'modal'       // Модальное окно
    };

    // Хранилище активных сообщений для отслеживания контекстов
    const activeMessages = new Map();

    /**
     * Показать сообщение
     * @param {string} text - Текст сообщения
     * @param {string} type - Тип сообщения (info, success, warning, error)
     * @param {string|Element} context - Контекст: 'main' для главного экрана или ID/элемент модалки
     * @param {number} duration - Длительность показа в мс (0 = не скрывать автоматически)
     */
    function show(text, type = MessageType.INFO, context = Context.MAIN, duration = 0) {
        const messageArea = getMessageArea(context);
        
        if (!messageArea) {
            console.error('[MessageManager] Не найдена область для сообщений:', context);
            console.error('[MessageManager] Сообщение:', text);
            // НЕ показываем fallback, только логируем ошибку
            return;
        }

        // Очищаем предыдущее содержимое
        messageArea.innerHTML = '';
        
        // Создаём текстовый элемент
        const textSpan = document.createElement('span');
        textSpan.style.cssText = 'white-space: pre-wrap; flex: 1;';
        textSpan.textContent = text;
        
        // Создаём кнопку закрытия (теперь всегда)
        const closeBtn = document.createElement('span');
        closeBtn.textContent = '×';
        closeBtn.style.cssText = 'cursor: pointer; font-size: 24px; font-weight: bold; margin-left: 15px; opacity: 0.7; flex-shrink: 0; line-height: 1;';
        closeBtn.title = 'Закрыть сообщение';
        closeBtn.onclick = () => hide(context);
        
        // Добавляем элементы
        messageArea.appendChild(textSpan);
        messageArea.appendChild(closeBtn);
        messageArea.style.display = 'flex';
        messageArea.style.alignItems = 'flex-start';
        messageArea.style.justifyContent = 'space-between';
        
        // Устанавливаем класс для стиля
        messageArea.className = 'message-area ' + type;

        // Сохраняем активное сообщение
        const contextKey = context instanceof Element ? 'element' : context;
        activeMessages.set(contextKey, { text, type, timestamp: Date.now() });

        // Логируем
        console.log(`[MessageManager] [${type.toUpperCase()}] ${text} (context: ${contextKey})`);

        // Автоматическое скрытие
        if (duration > 0) {
            setTimeout(() => {
                hide(context);
            }, duration);
        }
    }

    /**
     * Скрыть сообщение
     * @param {string|Element} context - Контекст сообщения
     */
    function hide(context = Context.MAIN) {
        const messageArea = getMessageArea(context);
        
        if (messageArea) {
            messageArea.style.display = 'none';
            messageArea.textContent = '';
            messageArea.className = 'message-area';
            
            // Удаляем из активных
            const contextKey = context instanceof Element ? 'element' : context;
            activeMessages.delete(contextKey);
        }
    }

    /**
     * Скрыть все сообщения кроме указанного контекста
     * @param {string} keepContext - Контекст, который НЕ нужно скрывать
     */
    function hideAllExcept(keepContext) {
        for (const [context] of activeMessages) {
            if (context !== keepContext) {
                hide(context);
            }
        }
    }

    /**
     * Получить элемент области сообщений
     * @param {string|Element} context - Контекст: 'main', ID модалки или элемент
     * @returns {Element|null}
     */
    function getMessageArea(context) {
        // Если передан элемент
        if (context instanceof Element) {
            return context.querySelector('.message-area');
        }

        // Если это главный экран
        if (context === Context.MAIN || context === 'main') {
            return document.getElementById('main-message-area');
        }

        // Если это ID модального окна
        const modalElement = document.getElementById(context);
        if (modalElement) {
            // Ищем как новую, так и старую разметку области сообщений
            const area = modalElement.querySelector('.message-area, .modal-message-area')
                || modalElement.querySelector('#rag-message-area');
            return area;
        }

        // Пробуем найти через data-атрибут
        const messageArea = document.querySelector(`[data-context="${context}"]`);
        if (messageArea) {
            return messageArea;
        }

        return null;
    }

    /**
     * Удобные методы для разных типов сообщений
     */
    const MessageManager = {
        // Показать сообщение
        show: show,
        
        // Скрыть сообщение
        hide: hide,
        
        // Показать информационное сообщение
        info: (text, context = Context.MAIN, duration = 5000) => {
            show(text, MessageType.INFO, context, duration);
        },
        
        // Показать сообщение об успехе
        success: (text, context = Context.MAIN, duration = 5000) => {
            show(text, MessageType.SUCCESS, context, duration);
        },
        
        // Показать предупреждение
        warning: (text, context = Context.MAIN, duration = 7000) => {
            show(text, MessageType.WARNING, context, duration);
        },
        
        // Показать ошибку
        error: (text, context = Context.MAIN, duration = 10000) => {
            show(text, MessageType.ERROR, context, duration);
        },
        
        // Показать на главном экране
        showMain: (text, type = MessageType.INFO, duration = 5000) => {
            show(text, type, Context.MAIN, duration);
        },
        
        // Показать в модалке
        showModal: (modalId, text, type = MessageType.INFO, duration = 5000) => {
            show(text, type, modalId, duration);
        },
        
        // Скрыть на главном экране
        hideMain: () => {
            hide(Context.MAIN);
        },
        
        // Скрыть в модалке
        hideModal: (modalId) => {
            hide(modalId);
        },
        
        // Скрыть все кроме указанного контекста
        hideAllExcept: hideAllExcept,
        
        // Константы
        Type: MessageType,
        Context: Context
    };

    // Автосброс сообщений при переходе между окнами
    // Отслеживаем открытие/закрытие модальных окон
    document.addEventListener('DOMContentLoaded', function() {
        // При клике на кнопки открытия модалок - скрываем сообщения других контекстов
        const modalTriggers = document.querySelectorAll('[onclick*="Modal"]');
        modalTriggers.forEach(trigger => {
            trigger.addEventListener('click', function() {
                const modalId = this.getAttribute('onclick').match(/['"]([^'"]+Modal)['"]/)?.[1];
                if (modalId) {
                    setTimeout(() => hideAllExcept(modalId), 100);
                }
            });
        });
        
        // При закрытии модалки - скрываем её сообщения
        const closeButtons = document.querySelectorAll('.close');
        closeButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const modal = this.closest('.modal');
                if (modal) {
                    hide(modal.id);
                }
            });
        });
    });

    // Экспортируем глобально
    window.MessageManager = MessageManager;
    
    // Обратная совместимость: глобальная функция showMessage
    window.showMessage = (text, type = 'info') => {
        MessageManager.show(text, type, Context.MAIN);
    };

    console.log('[MessageManager] Модуль загружен и готов к работе');

})();
