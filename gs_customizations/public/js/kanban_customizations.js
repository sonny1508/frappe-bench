/**
 * Kanban Customizations - Optimized & Consolidated
 * Combines: collapsible cards, inline editing, board filters, assignee name tags, scroll preservation
 * 
 * Performance fixes:
 * 1. Single MutationObserver with debouncing
 * 2. Targeted DOM observation (not document.body)
 * 3. Event listener cleanup on navigation
 * 4. WeakSet/WeakMap for processed element tracking
 * 5. RequestAnimationFrame for batch DOM updates
 * 6. Fixed double initialization of KanbanBoardCard override
 * 7. Added cleanup on route change
 * 8. Scroll position preservation on card drag/status change
 */

(function() {
    "use strict";

    const TARGET_DOCTYPE = "Task";

    // ==================== SHARED STATE ====================
    
    const state = {
        initialized: false,
        observer: null,
        themeObserver: null,
        appliedBoardFilter: null,
        routeListenerAttached: false,
        editableFieldTypes: null,
        kanbanCardOverridden: false,
        pendingRouteTimeout: null,
        blockBoardSwitch: false,
        originalFrappeCall: null, // Store original frappe.call for scroll preservation
    };

    // WeakSets to track processed elements (auto garbage-collected)
    const processedCards = {
        collapse: new WeakSet(),
        inlineEdit: new WeakSet(),
    };

    // ==================== PRIORITY CONFIG ====================

    const PRIORITY_ORDER = {
        "Urgent": 1,
        "High": 2,
        "Medium": 3,
        "Low": 4,
        "Support": 5,
    };

    // ==================== FIELD CONFIGURATIONS ====================

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
        custom_utilization: {
            fieldname: "custom_utilization",
            label: "Utilization",
            detectPatterns: ["Utilization"],
            readonly: true,
            isNumeric: true
        }
    };

    const optionsCache = {};

    // ==================== UTILITIES ====================

    function debounce(fn, delay) {
        let timeoutId;
        return function(...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function isKanbanView() {
        return !!(
            document.querySelector(".kanban") &&
            cur_list?.doctype === TARGET_DOCTYPE &&
            cur_list?.view_name === "Kanban"
        );
    }

    // ==================== SCROLL PRESERVATION ====================

    function getKanbanWrapper() {
        return cur_list?.kanban?.wrapper ? $(cur_list.kanban.wrapper) : null;
    }

    function getScrollableElement($col) {
        // Try common candidates for scrollable container
        let $scrollable = $col.find('.kanban-cards').first();
        if (!$scrollable.length) $scrollable = $col.find('.kanban-card-area').first();
        if (!$scrollable.length) $scrollable = $col.children().first();
        return $scrollable.length ? $scrollable : $col;
    }

    function captureScrollPositions() {
        const $wrapper = getKanbanWrapper();
        if (!$wrapper) return {};

        const positions = {};
        $wrapper.find('.kanban-column').each(function() {
            const colName = $(this).data('column-value');
            if (!colName) return;
            const $scrollable = getScrollableElement($(this));
            positions[colName] = $scrollable.scrollTop();
        });
        return positions;
    }

    function restoreScrollPositions(positions) {
        if (!positions || Object.keys(positions).length === 0) return;

        const $wrapper = getKanbanWrapper();
        if (!$wrapper) return;

        $wrapper.find('.kanban-column').each(function() {
            const colName = $(this).data('column-value');
            if (positions[colName]) {
                const $scrollable = getScrollableElement($(this));
                $scrollable.scrollTop(positions[colName]);
            }
        });
    }

    function patchFrappeCallForScrollPreservation() {
        // Already patched
        if (state.originalFrappeCall) return;

        state.originalFrappeCall = frappe.call;

        frappe.call = function(opts) {
            const isKanbanUpdate = opts.method && opts.method.includes('kanban');

            if (isKanbanUpdate && isKanbanView()) {
                const positions = captureScrollPositions();

                const originalCallback = opts.callback;
                opts.callback = function(r) {
                    if (originalCallback) {
                        originalCallback.call(this, r);
                    }
                    // Restore after callback and any subsequent renders
                    setTimeout(() => restoreScrollPositions(positions), 0);
                    setTimeout(() => restoreScrollPositions(positions), 100);
                    setTimeout(() => restoreScrollPositions(positions), 250);
                    setTimeout(() => restoreScrollPositions(positions), 500);
                };
            }

            return state.originalFrappeCall.apply(this, arguments);
        };
    }

    function unpatchFrappeCall() {
        if (state.originalFrappeCall) {
            frappe.call = state.originalFrappeCall;
            state.originalFrappeCall = null;
        }
    }

    // ==================== PERMISSIONS ====================

    function initPermissions() {
        if (state.editableFieldTypes) return; // Already initialized
        
        const managerRoles = frappe.boot.manager_roles || [];
        const userRoles = frappe.user_roles || [];
        const isManager = managerRoles.some(role => userRoles.includes(role));
        
        state.editableFieldTypes = new Set();
        for (const [fieldType, config] of Object.entries(FIELD_CONFIGS)) {
            if (config.readonly === true) {
                continue;
            }
            if (config.restricted !== true || isManager) {
                state.editableFieldTypes.add(fieldType);
            }
        }
    }

    function canEditField(fieldType) {
        return state.editableFieldTypes?.has(fieldType) ?? false;
    }

    // ==================== OPTION LOADING ====================

    async function loadFieldOptions(fieldType) {
        const config = FIELD_CONFIGS[fieldType];
        if (optionsCache[fieldType]) return optionsCache[fieldType];

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
            frappe.model.with_doctype(TARGET_DOCTYPE, function() {
                const field = frappe.meta.get_field(TARGET_DOCTYPE, fieldname);
                if (!field?.options) {
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


    // ==================== COLLAPSIBLE CARDS ====================

    function enhanceCardCollapse(card) {
        if (processedCards.collapse.has(card)) return;
        processedCards.collapse.add(card);

        const btn = document.createElement("button");
        btn.className = "kanban-toggle-btn";
        btn.title = "Toggle details";
        btn.innerHTML = frappe.utils.icon("expand", "sm");

        const toggle = () => {
            const expanded = card.classList.toggle("expanded");
            btn.innerHTML = frappe.utils.icon(expanded ? "collapse" : "expand", "sm");
        };

        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggle();
        });

        card.addEventListener("click", (e) => {
            if (e.target.closest("a")) return;
            if (card.classList.contains("expanded")) return;
            e.preventDefault();
            e.stopPropagation();
            toggle();
        });

        card.appendChild(btn);
    }

    // ==================== INLINE EDIT ====================

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
            return match ? Math.round(parseInt(match[1], 10) / 10) * 10 : 0;
        } else {
            const colonIndex = text.indexOf(":");
            return colonIndex !== -1 ? text.substring(colonIndex + 1).trim() : text.trim();
        }
    }

    function enhanceCardInlineEdit($wrapper) {
        const wrapperEl = $wrapper[0];
        if (processedCards.inlineEdit.has(wrapperEl)) return;
        processedCards.inlineEdit.add(wrapperEl);

        // Try to get docname from wrapper or inner card
        let docname = $wrapper.attr("data-name") || "";
        if (!docname) {
            const $innerCard = $wrapper.find(".kanban-card");
            docname = $innerCard.attr("data-name") || "";
        }
        docname = decodeURIComponent(docname);
        if (!docname) return;

        const $docContent = $wrapper.find(".kanban-card-doc");
        if (!$docContent.length) return;

        $docContent.children("div").each(function() {
            const $div = $(this);
            const fieldType = detectFieldType($div);
            if (!fieldType || !canEditField(fieldType)) return;

            const config = FIELD_CONFIGS[fieldType];
            const currentValue = extractCurrentValue($div, fieldType);

            $div.addClass("kanban-inline-editable")
                .attr("data-field-type", fieldType)
                .attr("data-fieldname", config.fieldname)
                .attr("data-docname", docname)
                .attr("data-current-value", currentValue)
                .attr("title", `Click to edit ${config.label}`);
        });
    }

    // ==================== ASSIGNEE NAMES ====================

    // Override KanbanBoardCard to render names instead of avatars
    function overrideKanbanBoardCard() {
        // Prevent multiple override attempts
        if (state.kanbanCardOverridden) return;
        
        const checkAndOverride = () => {
            // Double-check in case of race condition
            if (state.kanbanCardOverridden) return;
            
            if (!frappe.views.KanbanBoardCard) {
                setTimeout(checkAndOverride, 50);
                return;
            }
            
            // Mark as overridden BEFORE doing the override to prevent races
            state.kanbanCardOverridden = true;

            frappe.views.KanbanBoardCard = function(card, wrapper) {
                var self = {};

                function init() {
                    if (!card) return;
                    make_dom();
                    render_card_meta();
                }

                function make_dom() {
                    var opts = {
                        name: card.name,
                        title: frappe.utils.html2text(card.title),
                        disable_click: card._disable_click ? "disable-click" : "",
                        creation: card.creation,
                        doc_content: get_doc_content(card),
                        image_url: cur_list.get_image_url(card),
                        form_link: frappe.utils.get_form_link(card.doctype, card.name),
                    };

                    self.$card = $(frappe.render_template("kanban_card", opts)).appendTo(wrapper);

                    if (!frappe.model.can_write(card.doctype)) {
                        self.$card.find(".kanban-card-body").css("cursor", "default");
                    }
                }

                function get_doc_content(card) {
                    let fields = [];

                    cur_list.board.fields = cur_list.board.fields.map(f =>
                        f === "progress" ? "custom_utilization" : f
                    );

                    for (let field_name of cur_list.board.fields) {
                        let field =
                            frappe.meta.docfield_map[card.doctype]?.[field_name] ||
                            frappe.model.get_std_field(field_name);
                        let label = cur_list.board.show_labels
                            ? `<span>${__(field.label, null, field.parent)}: </span>`
                            : "";
                        let value = frappe.format(card.doc[field_name], field);
                        
                        // Add data attribute for Task Type field
                        const isTaskType = field.fieldtype === "Link" && field.options === "Task Type";
                        const inlineStyle = isTaskType ? '' : 'display: none;';
                        
                        const extraClass = field_name === "custom_utilization" ? "kanban-show-default" : "";

                        fields.push(`
                            <div class="text-muted text-truncate ${extraClass}" style="${inlineStyle}">
                                ${label}
                                <span>${value}</span>
                            </div>
                        `);
                    }
                    return fields.join("");
                }

                function get_tags_html(card) {
                    return card.tags
                        ? `<div class="kanban-tags">
                            ${cur_list.get_tags_html(card.tags, 3, true)}
                        </div>`
                        : "";
                }

                function render_card_meta() {
                    let html = get_tags_html(card);

                    if (card.comment_count > 0)
                        html += `<span class="list-comment-count small text-muted ">
                            ${frappe.utils.icon("es-line-chat-alt")}
                            ${card.comment_count}
                        </span>`;

                    const $assignees_group = get_assignees_as_names();

                    html += `
                        <span class="kanban-assignments"></span>
                        ${cur_list.get_like_html(card)}
                    `;

                    if (card.color && frappe.ui.color.validate_hex(card.color)) {
                        const $div = $("<div>");
                        $("<div></div>")
                            .css({
                                width: "30px",
                                height: "4px",
                                borderRadius: "2px",
                                marginBottom: "8px",
                                backgroundColor: card.color,
                            })
                            .appendTo($div);

                        self.$card.find(".kanban-card .kanban-title-area").prepend($div);
                    }

                    self.$card
                        .find(".kanban-card-meta")
                        .empty()
                        .append(html)
                        .find(".kanban-assignments")
                        .append($assignees_group);
                }

                function get_assignees_as_names() {
                    const $container = $('<div class="avatar-group"></div>');
                    
                    if (card.assigned_list && card.assigned_list.length) {
                        const $namesContainer = $('<div class="kanban-assignee-names"></div>');
                        
                        card.assigned_list.forEach(user => {
                            const fullName = frappe.user.full_name(user);
                            $namesContainer.append(
                                `<span class="kanban-assignee-tag">${frappe.utils.escape_html(fullName)}</span>`
                            );
                        });
                        
                        $container.append($namesContainer);
                    }

                    // Add the "+" button
                    const $addBtn = $(`
                        <span class="avatar avatar-small kanban-add-assignment" data-doctype="${card.doctype}" data-name="${card.name}">
                            <span class="avatar-action">${frappe.utils.icon("add", "xs")}</span>
                        </span>
                    `);
                    $container.append($addBtn);

                    return $container;
                }

                init();
            };
        };

        checkAndOverride();
    }

    // Call early, before kanban loads
    overrideKanbanBoardCard();

    // ==================== DROPDOWN UI ====================

    function showDropdown($field, fieldType, docname, currentValue) {
        $(".kanban-inline-dropdown").remove();

        loadFieldOptions(fieldType).then(options => {
            const $dropdown = $('<div class="kanban-inline-dropdown"></div>');
            const rect = $field[0].getBoundingClientRect();

            $dropdown.css({
                top: rect.bottom + 4,
                left: rect.left
            });

            options.forEach(opt => {
                const $item = $(`<div class="kanban-inline-dropdown-item">${opt.display}</div>`);
                if (String(opt.value) === String(currentValue)) {
                    $item.addClass("selected");
                }
                $item.on("click", () => {
                    saveFieldValue($field, fieldType, docname, opt.value);
                    $dropdown.remove();
                });
                $dropdown.append($item);
            });

            $("body").append($dropdown);

            // Close on outside click
            setTimeout(() => {
                $(document).one("click", () => $dropdown.remove());
            }, 10);
        }).catch(err => {
            console.error("Failed to load options:", err);
            frappe.show_alert({ message: __("Failed to load options"), indicator: "red" });
        });
    }

    function saveFieldValue($field, fieldType, docname, newValue) {
        const config = FIELD_CONFIGS[fieldType];
        const saveVal = config.isNumeric ? parseInt(newValue, 10) : newValue;

        $field.addClass("kanban-inline-saving");

        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: TARGET_DOCTYPE,
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

    // ==================== CARD MOVEMENT & REORDERING ====================

    function moveCardToColumn($card, newStatus) {
        if (!$card.length) return;

        const $targetColumn = $(`.kanban-column[data-column-value="${newStatus}"]`);
        if (!$targetColumn.length) return;

        const $currentColumn = $card.closest(".kanban-column");
        if ($currentColumn.attr("data-column-value") === newStatus) return;

        const $targetCards = $targetColumn.find(".kanban-cards");
        if (!$targetCards.length) return;

        requestAnimationFrame(() => {
            $card.detach().appendTo($targetCards);
            updateColumnCount($currentColumn, -1);
            updateColumnCount($targetColumn, 1);
            reorderColumnByPriority($targetColumn, $card[0]);
        });
    }

    function reorderColumnByPriority($column, movedCard = null) {
        if (!$column?.length) return;

        const $cardsContainer = $column.find(".kanban-cards");
        if (!$cardsContainer.length) return;

        const cards = $cardsContainer.find(".kanban-card-wrapper").toArray();
        if (cards.length < 2) return;

        // Pre-extract priorities
        const cardPriorities = new Map();
        cards.forEach(card => {
            const $priorityField = $(card).find('[data-fieldname="priority"]');
            const priority = $priorityField.attr('data-current-value') || '';
            cardPriorities.set(card, PRIORITY_ORDER[priority] ?? 99);
        });

        cards.sort((a, b) => {
            const priorityDiff = cardPriorities.get(a) - cardPriorities.get(b);
            if (priorityDiff !== 0) return priorityDiff;
            
            // Same priority: moved card comes first
            if (movedCard) {
                if (a === movedCard) return -1;
                if (b === movedCard) return 1;
            }
            return 0;
        });

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

    // ==================== BOARD FILTERS ====================

    function applyBoardFilters() {
        const board = cur_list?.board;
        if (cur_list?.board?.fields) {
            cur_list.board.fields = ["status", "type", "custom_utilization"];
        }
        const boardName = board?.name;
        
        if (!boardName || state.appliedBoardFilter === boardName) return;
        if (!board?.filters) return;

        const filters = typeof board.filters === "string"
            ? JSON.parse(board.filters)
            : board.filters;

        if (!filters?.length) return;

        state.appliedBoardFilter = boardName;

        // filters.push([TARGET_DOCTYPE, "status", "!=", "Closed"]);

        cur_list.filter_area.clear();
        cur_list.filter_area.add(filters.map(f => [f[0], f[1], f[2], f[3]]));
    }

    // ==================== UNIFIED CARD PROCESSING ====================

    // Debounced function to process all new cards
    const processNewCards = debounce(() => {
        if (!isKanbanView()) return;

        // Collapsible uses .kanban-card
        const cards = document.querySelectorAll(".kanban-card");
        cards.forEach(card => {
            enhanceCardCollapse(card);
        });

        // Inline edit uses .kanban-card-wrapper
        const cardWrappers = document.querySelectorAll(".kanban-card-wrapper");
        cardWrappers.forEach(wrapper => {
            const $wrapper = $(wrapper);
            enhanceCardInlineEdit($wrapper);
        });
    }, 100); // 100ms debounce - prevents rapid-fire processing

    // ==================== OBSERVER SETUP ====================

    function setupObserver() {
        if (state.observer) {
            state.observer.disconnect();
        }

        state.observer = new MutationObserver((mutations) => {
            // Early exit if not on kanban view
            if (!isKanbanView()) return;

            // Check if any mutations involve kanban cards
            let hasRelevantChanges = false;
            for (const mutation of mutations) {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    // Check added nodes for kanban content
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            // Skip nodes we add ourselves (toggle buttons, dropdowns)
                            if (node.classList?.contains('kanban-toggle-btn') ||
                                node.classList?.contains('kanban-inline-dropdown')) {
                                continue;
                            }
                            
                            if (node.classList?.contains('kanban-card') ||
                                node.classList?.contains('kanban-card-wrapper') ||
                                node.classList?.contains('kanban-column') ||
                                node.querySelector?.('.kanban-card-wrapper')) {
                                hasRelevantChanges = true;
                                break;
                            }
                        }
                    }
                }
                if (hasRelevantChanges) break;
            }

            if (hasRelevantChanges) {
                processNewCards();
            }
        });

        // Observe only the main content area, not the entire body
        const targetNode = document.querySelector('.frappe-list') || 
                          document.querySelector('[data-page-container]') ||
                          document.body;

        state.observer.observe(targetNode, {
            childList: true,
            subtree: true
        });
    }

    // ==================== ROUTE CHANGE HANDLING ====================

    function onRouteChange() {
        // Clear any pending timeout to prevent accumulation
        if (state.pendingRouteTimeout) {
            clearTimeout(state.pendingRouteTimeout);
            state.pendingRouteTimeout = null;
        }
        
        // Small delay to let Frappe set up cur_list
        state.pendingRouteTimeout = setTimeout(() => {
            state.pendingRouteTimeout = null;
            
            if (isKanbanView()) {
                // Wait for any pending AJAX to complete
                if (cur_list?.$result?.hasClass('loading')) {
                    // Still loading, try again
                    state.pendingRouteTimeout = setTimeout(onRouteChange, 100);
                    return;
                }

                preloadOptions();
                applyBoardFilters();
                processNewCards();
                patchFrappeCallForScrollPreservation();
            } else {
                state.appliedBoardFilter = null;
            }
        }, 250);
    }

    // ==================== THEME CHANGE HANDLING ====================

    function setupThemeListener() {
        // Disconnect existing observer if any
        if (state.themeObserver) {
            state.themeObserver.disconnect();
        }
        
        state.themeObserver = new MutationObserver(() => {
            $(".kanban-inline-dropdown").remove();
        });

        state.themeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme"]
        });
    }

    // ==================== CLEANUP ====================
    
    function cleanup() {
        if (state.observer) {
            state.observer.disconnect();
            state.observer = null;
        }
        if (state.themeObserver) {
            state.themeObserver.disconnect();
            state.themeObserver = null;
        }
        if (state.pendingRouteTimeout) {
            clearTimeout(state.pendingRouteTimeout);
            state.pendingRouteTimeout = null;
        }

        unpatchFrappeCall();

        processedCards.collapse = new WeakSet();
        processedCards.inlineEdit = new WeakSet();

        Object.keys(optionsCache).forEach(key => delete optionsCache[key]);

        $(document).off("click.kanbanInlineEdit");
        $(document).off("page-change.kanbanCustom");
        state.routeListenerAttached = false;
        state.initialized = false;
        state.kanbanCardOverridden = false;
    }
    
    // Expose cleanup for debugging/testing
    window.cleanupKanbanCustomizations = cleanup;

    // ==================== INITIALIZATION ====================

    function init() {
        if (state.initialized) return;
        state.initialized = true;
        
        initPermissions();
        setupThemeListener();
        setupObserver();
        patchFrappeCallForScrollPreservation();

        // Set up route listener once
        if (!state.routeListenerAttached) {
            state.routeListenerAttached = true;
            
            // Use frappe's page-change event
            $(document).on("page-change.kanbanCustom", onRouteChange);
            
            // Handle initial load with delay (cur_list needs time to populate)
            state.pendingRouteTimeout = setTimeout(() => {
                state.pendingRouteTimeout = null;
                if (isKanbanView()) {
                    preloadOptions();
                    applyBoardFilters();
                    processNewCards();
                }
            }, 200);
        }


        // Single delegated listener for all assign buttons - replaces per-card listeners
        $(document).off("click.kanbanAssign").on("click.kanbanAssign", ".kanban-add-assignment", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const $btn = $(this);
            const doctype = $btn.attr("data-doctype");
            const docname = $btn.attr("data-name");
            
            if (!doctype || !docname) return;
            
            const assignTo = new frappe.ui.form.AssignToDialog({
                obj: {},
                method: "frappe.desk.form.assign_to.add",
                doctype: doctype,
                docname: docname,
                callback: function() {
                    // Refresh just this card's assignments
                    cur_list?.refresh();
                },
            });
            assignTo.dialog.show();
        });

        // Event delegation for inline edit clicks
        $(document).off("click.kanbanInlineEdit").on("click.kanbanInlineEdit", ".kanban-inline-editable", function(e) {
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

    // Force all task links in kanban to open in new tab
    $(document).on("mousedown.kanbanNewTab", '.kanban-card a[href^="/app/task/"]', function() {
        $(this).attr("target", "_blank");
    });

    
    // Force switching kanban board to open in new tab
    $(document).on("show.bs.dropdown shown.bs.dropdown", function(e) {
        // Only on Task Kanban view
        if (!isKanbanView()) return;

        // Check if this is the "Select Kanban" dropdown
        const $toggle = $(e.target).find('[data-toggle="dropdown"], .dropdown-toggle');
        if (!$toggle.find('.custom-btn-group-label').text().includes('Select Kanban')) return;
        
        const $dropdown = $(e.target).find('.dropdown-menu');
        if (!$dropdown.length) return;
        
        $dropdown.find('.menu-item-label[data-label]').each(function() {
            const label = $(this).attr("data-label");
            if (label === "Create%20New%20Kanban%20Board" || label === "Create New Kanban Board") return;
            
            const $link = $(this).closest("a");
            
            if (!$link.data("hijacked")) {
                $link.data("hijacked", true);
                
                // Remove ALL event handlers from this link
                $link.off();
                $link.find('*').off();
                
                // Remove onclick attribute
                $link.prop("onclick", null);
                $link.removeAttr("onclick");
                
                // Add our own click handler
                $link.on("click", function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    
                    const boardName = decodeURIComponent(label);
                    const url = `/app/task/view/kanban/${encodeURIComponent(boardName)}`;
                    
                    // Close dropdown
                    // $dropdown.removeClass("show").hide();
                    
                    // Open new tab
                    window.open(url, "_blank");
                    
                    return false;
                });
            }
        });
    });

    // Start initialization when DOM is ready
    $(document).ready(init);

})();