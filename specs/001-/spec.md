# Feature Specification: Обработка архивов как папок

**Feature Branch**: `001-`  
**Created**: 2025-09-30  
**Status**: Draft  
**Input**: User description: "проанализируй проект, сделай фичу по обработке архивов как папок, программа должна видеть архив как папку, и дальше обрабатывать ее так же как сейчас программа обрабатывает папку, т.е. извлекать и анализировать файлы. Все изменения и добавления в общий функционал программы должны работать и с архивами"

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
Пользователь загружает ZIP/RAR архив. В интерфейсе архив отображается как папка. Пользователь строит индекс, выполняет поиск, и видит результаты, включающие документы из архива с корректными путями и сниппетами.

### Acceptance Scenarios
1. Given загружен ZIP‑архив с вложенными папками и поддерживаемыми файлами, When пользователь строит индекс, Then индекс содержит записи для всех поддерживаемых файлов внутри архива с виртуальными путями вида `zip://<архив>/<внутренний_путь>`.
2. Given в системе есть индекс, включающий архивы, When пользователь выполняет поиск по словам, Then в результатах отображаются элементы из архивов со сниппетами и навигацией в UI.

### Edge Cases
- Повреждённый архив — помечается ошибочным; содержимое не индексируется; UI отражает статус.
- Неподдерживаемые файлы внутри архива — помечаются как неподдерживаемые; не извлекаются.
- Очень большие/глубокие архивы — индексация с ограничениями; система остаётся отзывчивой.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: Система ДОЛЖНА отображать архивы (ZIP, RAR) как виртуальные папки в дереве файлов.
- **FR-002**: Система ДОЛЖНА индексировать поддерживаемые файлы внутри архивов, используя виртуальные пути `zip://...` и `rar://...`.
- **FR-003**: Система ДОЛЖНА включать результаты из архивов в поиск и выдавать сниппеты наравне с обычными файлами.
- **FR-004**: Система ДОЛЖНА помечать ошибочные/неподдерживаемые элементы и не пытаться их открывать или скачивать (серо в UI, 403 в API).
- **FR-005**: Система ДОЛЖНА избегать тяжёлых операций в HTTP-запросах; извлечение выполняется в фазе индексации.
- **FR-006**: Система ДОЛЖНА обеспечивать безопасную обработку путей и извлечения (без traversal/zip-slip).
- **FR-007**: Система ДОЛЖНА вести логи ключевых событий при индексации архивов.
- **FR-008**: Система ДОЛЖНА определиться с поведением для вложенных архивов [NEEDS CLARIFICATION: поддерживать ли архивы внутри архивов?].
- **FR-009**: Система ДОЛЖНА отображать архивы и их содержимое в UI как обычные папки и файлы.
- **FR-010**: Система ДОЛЖНА хранить в индексе сведения, достаточные для корректной навигации и политик доступа к элементам архива.

### Key Entities *(include if feature involves data)*
- **Archive**: Виртуальная папка (имя, тип zip/rar, виртуальный корень, список элементов, статус).
- **ArchiveItem**: Элемент архива (внутренний путь, тип, статус, размер, хэш/mtime при наличии, char_count).

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
