/**
 * Kanban Inline Edit - Multi-Field Support
 */

(function() {
    "use strict";

    const DOCTYPE = "Task";

    const PRIORITY_ORDER = {
        "Urgent": 1,
        "High": 2,
        "Medium": 3,
        "Low": 4,
        "Support": 5,
    };

    // ========== FIELD CONFIGURATIONS ==========

    const FIELD_CONFIGS = {
        status: {
            fieldname: "status",
            label: "Status",
            detectPatterns: ["Status"],
            optionType: "select"
        },
        priority: {
            fieldname: "priority",
            label: "Priority",
            detectPatterns: ["Priority"],
            optionType: "select",
            restricted: true
        },
        type: {
            fieldname: "type",
            label: "Type",
            detectPatterns: ["Type"],
            optionType: "link",
            linkDoctype: "Task Type",
            restricted: true
        },
        progress: {
            fieldname: "progress",
            label: "Progress",
            detectPatterns: ["Progress", "%"],
            optionType: "static",
            options: [
                { value: 0, display: "0%" },
                { value: 10, display: "10%" },
                { value: 20, display: "20%" },
                { value: 30, display: "30%" },
                { value: 40, display: "40%" },
                { value: 50, display: "50%" },
                { value: 60, display: "60%" },
                { value: 70, display: "70%" },
                { value: 80, display: "80%" },
                { value: 90, display: "90%" },
                { value: 100, display: "100%" }
            ],
            isNumeric: true,
        }
    };

    const optionsCache = {};
    const enhancedCards = new WeakSet();

    // ========== PERMISSION CHECK ==========

    // Computed once on init
    let editableFieldTypes = null;

    function initPermissions() {
        const managerRoles = frappe.boot.manager_roles || [];
        const userRoles = frappe.user_roles || [];
        const isManager = managerRoles.some(role => userRoles.includes(role));
        
        // Pre-compute which fields this user can edit
        editableFieldTypes = new Set();
        for (const [fieldType, config] of Object.entries(FIELD_CONFIGS)) {
            if (config.restricted !== true || isManager) {
                editableFieldTypes.add(fieldType);
            }
        }
    }

    function canEditField(fieldType) {
        return editableFieldTypes.has(fieldType);
    }

    // ========== UTILITY: DEBOUNCE ==========

    function debounce(fn, delay) {
        let timeoutId;
        return function(...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    // ========== UTILITY: KANBAN VIEW DETECTION ==========

    function isKanbanView() {
        // Check if we're actually on a kanban board for Task
        return !!(
            document.querySelector(".kanban") &&
            cur_list?.doctype === DOCTYPE &&
            cur_list?.view_name === "Kanban"
        );
    }

    // ========== OPTION LOADING ==========

    async function loadFieldOptions(fieldType) {
        const config = FIELD_CONFIGS[fieldType];

        if (optionsCache[fieldType]) {
            return optionsCache[fieldType];
        }

        let options = [];

        if (config.optionType === "static") {
            options = config.options;
        } else if (config.optionType === "select") {
            options = await loadSelectOptions(config.fieldname);
        } else if (config.optionType === "link") {
            options = await loadLinkOptions(config.linkDoctype);
        }

        optionsCache[fieldType] = options;
        return options;
    }

    async function loadSelectOptions(fieldname) {
        return new Promise((resolve, reject) => {
            frappe.model.with_doctype(DOCTYPE, function() {
                const field = frappe.meta.get_field(DOCTYPE, fieldname);
                if (!field || !field.options) {
                    reject(new Error(`Could not load options for field: ${fieldname}`));
                    return;
                }
                const optionValues = field.options.split("\n").filter(opt => opt.trim());
                resolve(optionValues.map(value => ({
                    value: value.trim(),
                    display: value.trim()
                })));
            });
        });
    }

    async function loadLinkOptions(linkDoctype) {
        return new Promise((resolve, reject) => {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: linkDoctype,
                    fields: ["name"],
                    limit_page_length: 0,
                    order_by: "name asc"
                },
                async: true,
                callback: function(r) {
                    if (r.exc || !r.message) {
                        reject(new Error(`Could not load options from: ${linkDoctype}`));
                        return;
                    }
                    resolve(r.message.map(doc => ({
                        value: doc.name,
                        display: doc.name
                    })));
                },
                error: () => reject(new Error(`Failed to fetch from: ${linkDoctype}`))
            });
        });
    }

    // Preload options when entering kanban view
    function preloadOptions() {
        Object.keys(FIELD_CONFIGS).forEach(fieldType => {
            loadFieldOptions(fieldType).catch(() => {});
        });
    }

    function clearOptionsCache(fieldType) {
        if (fieldType) {
            delete optionsCache[fieldType];
        } else {
            Object.keys(optionsCache).forEach(key => delete optionsCache[key]);
        }
    }

    window.clearKanbanOptionsCache = clearOptionsCache;

    // ========== THEME DETECTION ==========

    function isDarkTheme() {
        return document.documentElement.getAttribute("data-theme") === "dark";
    }

    // ========== FIELD DETECTION ==========

    function detectFieldType($div) {
        const text = $div.text();
        for (const [key, config] of Object.entries(FIELD_CONFIGS)) {
            if (config.detectPatterns.some(pattern => text.includes(pattern))) {
                return key;
            }
        }
        return null;
    }

    function extractCurrentValue($div, fieldType) {
        const config = FIELD_CONFIGS[fieldType];
        const text = $div.text();

        if (config.isNumeric) {
            const match = text.match(/(\d+)[,.]?\d*/);
            if (match) {
                return Math.round(parseInt(match[1], 10) / 10) * 10;
            }
            return 0;
        } else {
            const colonIndex = text.indexOf(":");
            return colonIndex !== -1 ? text.substring(colonIndex + 1).trim() : text.trim();
        }
    }

    // ========== CARD ENHANCEMENT ==========

    function enhanceCard($card) {
        if (enhancedCards.has($card[0])) return;
        enhancedCards.add($card[0]);

        const docname = decodeURIComponent($card.attr("data-name") || "");
        if (!docname) return;

        const $docContent = $card.find(".kanban-card-doc");
        if (!$docContent.length) return;

        $docContent.children("div").each(function() {
            const $div = $(this);
            const fieldType = detectFieldType($div);
            if (!fieldType) return;

            // Skip restricted fields for non-managers
            if (!canEditField(fieldType)) return;

            const currentValue = extractCurrentValue($div, fieldType);
            const config = FIELD_CONFIGS[fieldType];

            $div.addClass("kanban-inline-editable")
                .attr("data-field-type", fieldType)
                .attr("data-fieldname", config.fieldname)
                .attr("data-docname", docname)
                .attr("data-current-value", currentValue);
        });
    }

    /**
     * Enhanced: Only process new/unenhanced cards
     */
    function enhanceNewCards($container) {
        if (!isKanbanView()) return;

        const $cards = $container 
            ? $container.find(".kanban-card-wrapper")
            : $(".kanban-card-wrapper");

        $cards.each(function() {
            if (!enhancedCards.has(this)) {
                enhanceCard($(this));
            }
        });
    }

    // Debounced version for mutation observer
    const debouncedEnhance = debounce(() => enhanceNewCards(), 100);

    // ========== MUTATION OBSERVER ==========

    function setupObserver() {
        const observer = new MutationObserver(function(mutations) {
            if (!isKanbanView()) return;

            let hasNewCards = false;

            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType !== Node.ELEMENT_NODE) continue;

                    const $node = $(node);
                    if ($node.hasClass("kanban-card-wrapper") ||
                        $node.find(".kanban-card-wrapper").length) {
                        hasNewCards = true;
                        break;
                    }
                }
                if (hasNewCards) break;
            }

            if (hasNewCards) {
                debouncedEnhance();
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        return observer;
    }

    // ========== DROPDOWN UI ==========

    async function showDropdown($field, fieldType, docname, currentValue) {
        $(".kanban-inline-dropdown").remove();

        let options;
        try {
            options = await loadFieldOptions(fieldType);
        } catch (error) {
            frappe.show_alert({
                message: __("Failed to load options: {0}", [error.message]),
                indicator: "red"
            });
            return;
        }

        if (!options || options.length === 0) {
            frappe.show_alert({
                message: __("No options available for {0}", [FIELD_CONFIGS[fieldType].label]),
                indicator: "orange"
            });
            return;
        }

        const optionsHtml = options.map(opt => {
            const isSelected = String(opt.value) === String(currentValue) ? "selected" : "";
            return `<div class="kanban-inline-option ${isSelected}" data-value="${opt.value}">
                <span class="kanban-inline-label">${opt.display || opt.value}</span>
            </div>`;
        }).join("");

        const $dropdown = $(`<div class="kanban-inline-dropdown" data-field-type="${fieldType}">${optionsHtml}</div>`);

        const rect = $field[0].getBoundingClientRect();
        let top = rect.bottom + 4;
        let left = rect.left;

        $("body").append($dropdown);

        const dropdownRect = $dropdown[0].getBoundingClientRect();
        if (top + dropdownRect.height > window.innerHeight) {
            top = rect.top - dropdownRect.height - 4;
        }
        if (left + dropdownRect.width > window.innerWidth) {
            left = window.innerWidth - dropdownRect.width - 10;
        }

        $dropdown.css({ top: top + "px", left: left + "px" });

        $dropdown.on("click", ".kanban-inline-option", function(e) {
            e.stopPropagation();
            e.preventDefault();

            const newValue = $(this).attr("data-value");
            $dropdown.remove();

            if (String(newValue) !== String(currentValue)) {
                saveValue(fieldType, docname, newValue, $field);
            }
        });

        setTimeout(() => {
            $(document).one("click.kanban-dropdown", () => $dropdown.remove());
        }, 10);
    }

    // ========== SAVE FUNCTIONALITY ==========

    function saveValue(fieldType, docname, newValue, $field) {
        const config = FIELD_CONFIGS[fieldType];
        const saveVal = config.isNumeric ? parseFloat(newValue) : newValue;

        $field.addClass("kanban-inline-saving");

        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: DOCTYPE,
                name: docname,
                fieldname: config.fieldname,
                value: saveVal
            },
            callback: function(r) {
                $field.removeClass("kanban-inline-saving");

                if (r.exc) {
                    frappe.show_alert({
                        message: __("Failed to update {0}", [config.label]),
                        indicator: "red"
                    });
                    return;
                }

                $field.attr("data-current-value", newValue);
                updateFieldDisplay($field, fieldType, newValue);

                frappe.show_alert({
                    message: __("{0} updated to {1}", [config.label, getDisplayValue(fieldType, newValue)]),
                    indicator: "green"
                }, 3);

                if (config.fieldname === "status") {
                    moveCardToColumn($field.closest(".kanban-card-wrapper"), newValue);
                }

                if (config.fieldname === "priority") {
                    reorderColumnByPriority($field.closest(".kanban-column"));
                }
            },
            error: function() {
                $field.removeClass("kanban-inline-saving");
                frappe.show_alert({
                    message: __("Error updating {0}", [config.label]),
                    indicator: "red"
                });
            }
        });
    }

    function getDisplayValue(fieldType, value) {
        const config = FIELD_CONFIGS[fieldType];
        if (config.isNumeric && config.options) {
            const opt = config.options.find(o => o.value === parseInt(value, 10));
            return opt ? opt.display : value + "%";
        }
        return value;
    }

    function updateFieldDisplay($field, fieldType, newValue) {
        const displayValue = getDisplayValue(fieldType, newValue);
        const $spans = $field.find("span");

        if ($spans.length >= 2) {
            $spans.last().text(displayValue);
        } else if ($spans.length === 1) {
            $spans.text(displayValue);
        } else {
            const currentText = $field.text();
            const labelMatch = currentText.match(/^([^:]+:\s*)/);
            $field.text(labelMatch ? labelMatch[1] + displayValue : displayValue);
        }
    }

    // ========== CARD MOVEMENT ==========

    function moveCardToColumn($card, newStatus) {
        if (!$card.length) return;

        const $targetColumn = $(`.kanban-column[data-column-value="${newStatus}"]`);
        if (!$targetColumn.length) return;

        const $currentColumn = $card.closest(".kanban-column");
        if ($currentColumn.attr("data-column-value") === newStatus) return;

        const $targetCards = $targetColumn.find(".kanban-cards");
        if (!$targetCards.length) return;

        // Batch DOM update
        requestAnimationFrame(() => {
            $card.detach().appendTo($targetCards);
            updateColumnCount($currentColumn, -1);
            updateColumnCount($targetColumn, 1);
            // Reorder after move
            reorderColumnByPriority($targetColumn);
        });
    }

    /**
     * Optimized: Reorder a single column, batch DOM writes
     */
    function reorderColumnByPriority($column) {
        if (!$column || !$column.length) return;

        const $cardsContainer = $column.find(".kanban-cards");
        if (!$cardsContainer.length) return;

        const cards = $cardsContainer.find(".kanban-card-wrapper").toArray();
        if (cards.length < 2) return;

        // Pre-extract priorities (avoid DOM reads during sort)
        const cardPriorities = new Map();
        cards.forEach(card => {
            const $priorityField = $(card).find('[data-fieldname="priority"]');
            const priority = $priorityField.attr('data-current-value') || '';
            cardPriorities.set(card, PRIORITY_ORDER[priority] ?? 99);
        });

        // Sort using cached values
        cards.sort((a, b) => cardPriorities.get(a) - cardPriorities.get(b));

        // Batch DOM writes using DocumentFragment
        requestAnimationFrame(() => {
            const fragment = document.createDocumentFragment();
            cards.forEach(card => fragment.appendChild(card));
            $cardsContainer[0].appendChild(fragment);
        });
    }

    function updateColumnCount($column, delta) {
        const $count = $column.find(".column-card-count, .kanban-column-count");
        if ($count.length) {
            const current = parseInt($count.text(), 10) || 0;
            $count.text(current + delta);
        }
    }

    // ========== DRAG DROP SYNC ==========

    function setupDragDropSync() {
        // Instead of monkey-patching unfreeze, listen to specific kanban events
        // or use a more targeted approach
        
        // Option 1: Listen to frappe's kanban-specific events if available
        $(document).on('kanban:card:drop', syncAfterDragDrop);
        
        // Option 2: Debounced, conditional sync on route change TO kanban
        frappe.router.on('change', () => {
            if (isKanbanView()) {
                debouncedSyncColumns();
            }
        });
    }

    const debouncedSyncColumns = debounce(() => {
        if (!isKanbanView()) return;
        syncAllCardsWithColumns();
    }, 250);

    function syncAfterDragDrop() {
        if (!isKanbanView()) return;
        
        requestAnimationFrame(() => {
            syncAllCardsWithColumns();
        });
    }

    function syncAllCardsWithColumns() {
        const columns = document.querySelectorAll('.kanban-column');
        
        columns.forEach(column => {
            const $column = $(column);
            const columnStatus = $column.attr('data-column-value');
            if (!columnStatus) return;

            // Update status displays
            $column.find('.kanban-card-wrapper').each(function() {
                const $statusField = $(this).find('[data-fieldname="status"]');
                if ($statusField.length && $statusField.attr('data-current-value') !== columnStatus) {
                    $statusField.attr('data-current-value', columnStatus);
                    updateFieldDisplay($statusField, 'status', columnStatus);
                }
            });

            // Reorder this column
            reorderColumnByPriority($column);
        });
    }

    // ========== THEME CHANGE LISTENER ==========

    function setupThemeListener() {
        const observer = new MutationObserver(() => {
            $(".kanban-inline-dropdown").remove();
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme"]
        });
    }

    // ========== INITIALIZATION ==========

    let observerInstance = null;

    function init() {
        initPermissions();
        setupThemeListener();
        setupDragDropSync();

        // Always set up the observer once (it has internal guards)
        if (!observerInstance) {
            observerInstance = setupObserver();
        }

        // Try initial enhancement with a small delay for cur_list to populate
        setTimeout(() => {
            if (isKanbanView()) {
                preloadOptions();
                enhanceNewCards();
            }
        }, 100);

        // Re-init when navigating to kanban view
        $(document).on("page-change", () => {
            // Delay to let Frappe set up cur_list
            setTimeout(() => {
                if (isKanbanView()) {
                    preloadOptions();
                    enhanceNewCards();
                }
            }, 150);
        });

        // Event delegation for clicking editable fields
        $(document).on("click", ".kanban-inline-editable", function(e) {
            e.stopPropagation();
            e.preventDefault();

            const $field = $(this);
            const fieldType = $field.attr("data-field-type");
            const docname = $field.attr("data-docname");
            const currentValue = $field.attr("data-current-value");

            if (docname && fieldType) {
                showDropdown($field, fieldType, docname, currentValue);
            }
        });
    }

    $(document).ready(init);

})();