# Feature Specification: Просмотр неподдерживаемых файлов и интеграция результатов в разделе «Файлы»

**Feature Branch**: `001-1-json-2`  
**Created**: 2025-10-01  
**Status**: Draft  
**Input**: User description: "Постановка: 1) При клике на файлы, которые не прочитаны, в новом окне вместо JSON нужно выдавать сообщение, что просмотр файла не поддерживается, для реальных и виртуальных файлов. 2) Убрать отдельный блок результатов; выводить результаты под каждым файлом в разделе 'Файлы': количество сниппетов=2, шрифт чуть меньше; ключевое слово, счётчик, голубые полоски остаются. 3) Удалить блок очистка и кнопку 'Очистить всё'; объединить кнопки 'Выбрать папку', 'Удалить файлы' и 'Просмотр' на одной линии; переименовать 'Просмотр' в 'Просмотр индекса'; область назвать 'Инструменты'; статус загрузки сводного файла перенести в 'Инструменты' под кнопками. Функциональность (кликабельность ссылок, открытие документов, светофоры, загрузка/очистка, счётчики слов и подсветка) должна сохраниться. На это нужно написать автотесты."

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies  
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
Пользователь управляет документами и результатами поиска в одном разделе «Файлы», ожидая предсказуемого поведения при клике по файлам, просмотре индекса и работе с инструментами без потери существующей функциональности.

### Acceptance Scenarios
1. Given файл имеет статус «не прочитан/ошибка/char_count=0» (реальный или виртуальный), When пользователь кликает по нему (просмотр), Then открывается новая вкладка с понятным сообщением: «Просмотр файла не поддерживается» (без JSON-содержимого).
2. Given выполнен поиск, When пользователь открывает раздел «Файлы», Then под каждым файлом отображаются результаты поиска по этому файлу (до 2 сниппетов на термин) с прежней визуальной кодировкой (ключевое слово, счётчик, голубые полоски), шрифт сниппетов немного меньше основного.
3. Given интерфейс, When пользователь смотрит на панель «Инструменты», Then он видит на одной линии кнопки «Выбрать папку», «Удалить файлы», «Просмотр индекса», а ниже — статус сводного файла индекса.
4. Given интерфейс, When пользователь ищет или открывает документы, Then кликабельность ссылок, светофоры, загрузка/удаление файлов, счётчики слов и подсветка сниппетов работают как в текущей версии.

### Edge Cases
- Клик по виртуальному файлу из архива с ошибкой индексации (или 0 символов) показывает сообщение «Просмотр файла не поддерживается».
- Отсутствие результатов по файлу не должно ломать верстку — под файлом либо скрытый блок, либо пустой индикатор.
- Большое количество терминов: вывод ограничен, но счётчики по каждому термину корректны.
- Удаление файлов/папок не должно оставлять «висячие» блоки результатов.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: При клике на файл со статусом неподдерживаемого просмотра (unsupported/error/char_count=0) система должна открывать страницу с сообщением «Просмотр файла не поддерживается» (без вывода JSON/сырого контента).
- **FR-002**: Правило FR-001 распространяется как на реальные файлы из uploads, так и на виртуальные файлы из архивов (zip/rar) в разделе «Файлы».
- **FR-003**: Отдельный блок результатов поиска должен быть удалён; результаты отображаются непосредственно под каждым файлом в разделе «Файлы».
- **FR-004**: Для каждого файла показывать до 2 сниппетов на термин (при наличии), сохраняя визуальные элементы: ключевое слово, количество совпадений, голубые полоски слева.
- **FR-005**: Шрифт сниппетов под файлами должен быть немного меньше основного шрифта списка файлов.
- **FR-006**: Панель «Инструменты» должна включать на одной линии кнопки: «Выбрать папку», «Удалить файлы», «Просмотр индекса». Кнопка «Просмотр» переименована в «Просмотр индекса».
- **FR-007**: Статус сводного файла индекса должен отображаться в панели «Инструменты» под кнопками.
- **FR-008**: Блок «Очистка» и кнопка «Очистить всё» должны быть удалены. Функция удаления файлов (и папок) остаётся доступной и работоспособной.
- **FR-009**: Сохранить текущую функциональность: кликабельность ссылок, открытие документов (там, где это поддерживается), светофоры, загрузку и удаление файлов, корректные счётчики по терминам и подсветку сниппетов.
- **FR-010**: Добавить автотесты, покрывающие: (а) сообщение «Просмотр файла не поддерживается» для неподдерживаемых/ошибочных/0-символьных файлов (реальных и виртуальных); (б) вывод результатов под файлами (по 2 сниппета); (в) корректность панели «Инструменты» и отсутствие старых элементов («Очистка», отдельный блок результатов).

### Key Entities *(include if feature involves data)*
- **File Item**: карточка файла в разделе «Файлы», включает название, размер, светофор, и подблок результатов.
- **Tools Panel**: панель «Инструменты» с кнопками и статусом индекса.
- **Search Result Snippets**: до 2 сниппетов на термин, с меткой термина, счётчиком и визуальным маркером.

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous  
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [ ] User description parsed
- [ ] Key concepts extracted
- [ ] Ambiguities marked
- [ ] User scenarios defined
- [ ] Requirements generated
- [ ] Entities identified
- [ ] Review checklist passed

---
