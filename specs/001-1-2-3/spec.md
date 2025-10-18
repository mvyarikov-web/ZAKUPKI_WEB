# Feature Specification: Инкремент 13 — Быстрый и качественный OCR с приоритетной индексацией текстовых файлов

**Feature Branch**: `001-1-2-3`  
**Created**: 2025-10-18  
**Status**: Draft  
**Input**: Пользователь описал три задачи: (1) OCR по изображениям работает медленно — требуется серьёзное ускорение; (2) качество распознавания низкое — сфокусироваться на английском и русском алфавитах; (3) индекс нужно формировать в первую очередь из файлов с текстом, а OCR делать вторым этапом; пользователь должен сразу работать с уже готовыми файлами, а после завершения распознавания картинок по каждому файлу применять текущие поисковые термины и обновлять результаты. Важно ничего не сломать из текущего функционала.

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
Как пользователь веб-интерфейса поиска, я хочу, чтобы система быстро давала возможность искать по всем загруженным документам: сразу — по тем, где уже есть текст (PDF/DOCX/TXT и др.), и по мере готовности — добавляла результаты по отсканированным изображениям/PDF после их распознавания, чтобы мне не ждать окончания всего OCR-процесса.

### Acceptance Scenarios
1. Given загруженная смешанная папка (текстовые файлы + сканы), When пользователь запускает индексацию, Then индекс создаётся из текстовых файлов в течение оговорённого времени, поиск по ним доступен немедленно, и UI отображает, что OCR по сканам идёт в фоне.
2. Given идут фоновые OCR-задачи, When завершается распознавание очередного файла-скана, Then текущий поисковый запрос автоматически применяется к новому контенту, и результаты поиска дополняются без перезагрузки страницы, с пометкой о догрузке.
3. Given пользователь задал поисковые термины, When OCR завершён по всем релевантным файлам, Then результаты консистентны: включают и текстовые, и распознанные источники, без дубликатов и с корректными сниппетами.
4. Given слабая машина/ограниченный бюджет, When OCR длится дольше, чем весь текстовый проход, Then UI продолжает показывать прогресс и позволяет работать с уже доступной частью индекса; таймауты и ошибки сообщаются в дружественной форме.

### Edge Cases
- Папка содержит только сканы: первый этап индексации почти пуст, но UI ясно показывает, что OCR идёт и прогресс движется; результаты появляются по мере готовности.
- Очень большой архив со сканами: OCR распараллелен/пакетирован в безопасных для среды пределах; отмена/повтор возможны без падений.
- Низкое качество изображений: система ограниченно улучшает читабельность (не обесцвечивает бизнес-логику), но сообщает, если качество слишком низкое для уверенного поиска.
- Отсутствуют системные зависимости OCR: система не падает, а чётко сообщает об ограниченном режиме без OCR и предлагает альтернативы.

## Requirements *(mandatory)*

### Functional Requirements
- FR-001 Приоритетная индексация: система должна сначала индексировать все файлы, из которых можно извлечь текст без OCR, и формировать частичный индекс, доступный для поиска сразу после завершения этого этапа.
- FR-002 Фоновый OCR-этап: система должна запускать OCR для файлов-сканов вторым этапом без блокировки работы поиска по уже проиндексированным текстовым файлам.
- FR-003 Инкрементальное обновление поиска: по завершении OCR каждого отдельного файла система должна автоматически применять текущие поисковые термины и догружать результаты в интерфейс без перезагрузки.
- FR-004 Фокус языков: распознавание должно быть настроено на языки русского и английского алфавитов, обеспечивая преимущественно высокое качество для них.
- FR-005 Производительность OCR: время распознавания должно быть существенно сокращено относительно текущего состояния; целевой ориентир — не хуже X страниц в минуту на эталонном окружении [NEEDS CLARIFICATION: указать метрику X и эталон].
- FR-006 Прогресс и статусы: интерфейс должен отображать понятный прогресс по двум этапам (индексация текста, OCR сканов), количество обработанных/оставшихся файлов и статус последней операции, а также дружелюбные сообщения об ошибках.
- FR-007 Устойчивость: при отсутствии системных зависимостей (tesseract/unrar/poppler) система должна продолжать работать в ограниченном режиме (только текстовый этап), логировать предупреждения и информировать пользователя.
- FR-008 Консистентность результатов: в выдаче не должно быть дубликатов; результаты должны корректно объединять контент из текстового и OCR-этапов, с правильными сниппетами и подсветкой совпадений.
- FR-009 Контроль нагрузки: система должна ограничивать параллелизм OCR в рамках доступных ресурсов, избегая деградации работы основного поиска и UI.
- FR-010 Обратимая остановка: пользователь должен иметь возможность прервать фоновый OCR-процесс без потери уже сформированного индекса; при повторном запуске обработка продолжается с пропуском уже готовых файлов.
- FR-011 Совместимость: новое поведение не должно ломать уже существующие сценарии загрузки, индексации, поиска и логирования.

Примечания к прояснению:
- [NEEDS CLARIFICATION] Уточнить целевые SLA/метрики скорости OCR (страниц/мин) и допустимое использование ресурсов (CPU/GPU/память).
- [NEEDS CLARIFICATION] Уточнить ограничение на параллелизм OCR (например, N одновременных задач) и приоритеты в очереди.
- [NEEDS CLARIFICATION] Уточнить UX требований к «догрузке» результатов (анимация, пометки, сортировка по времени появления или релевантности).
- [NEEDS CLARIFICATION] Уточнить длительность и формат хранения промежуточных статусов (для возобновления после перезапуска сервиса).

### Key Entities *(include if feature involves data)*
- Entity: «Документ» — уникальный источник (файл или виртуальный элемент из архива), атрибуты: тип содержимого (текст/скан), статус обработки (не начата/индексирована/OCR в очереди/OCR готов/ошибка), языковая гипотеза (rus/eng), дата обновления, счётчик символов.
- Entity: «Индексная запись» — ссылка на документ + извлечённый текстовый контент + метаданные (источник, флаги OCR, качество распознавания), принадлежность к этапу (текст/ocr).
- Entity: «Очередь OCR» — FIFO (или приоритетная) очередь задач распознавания с ограничением параллелизма, атрибуты: документ, статус, таймстемпы, попытки.
- Entity: «Статус индексации» — агрегаты по прогрессу текстового и OCR-этапов, метрики скорости, ошибки.


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
