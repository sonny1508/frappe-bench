/**
 * Kanban Customizations - Optimized & Consolidated
 * Combines: collapsible cards, inline editing, board filters, assignee name tags, scroll preservation
 *
 * Render-path:
 * - Inline-edit attrs and collapse toggle are baked into the KanbanBoardCard
 *   template (no post-render scan, no MutationObserver).
 * - board.fields normalized once per board (not per card).
 * - docfield_map cached per card (not per field).
 * - Field options loaded lazily on first dropdown open.
 * - Toggle/expand/inline-edit/assign clicks are delegated.
 * - A refresh redraws only the cards, only if the data changed, never mid-drag.
 */

(function() {
    "use strict";

    const TARGET_DOCTYPE = "Task";

    // ==================== SHARED STATE ====================
    
    const state = {
        initialized: false,
        themeObserver: null,
        appliedBoardFilter: null,
        routeListenerAttached: false,
        editableFieldTypes: null,
        kanbanCardOverridden: false,
        pendingRouteTimeout: null,
        blockBoardSwitch: false,
        originalFrappeCall: null,
        boardFieldsNormalized: null, // Board name for which fields were already normalized
        renderPatched: false,
        shownBoard: null, // The list view whose board Frappe's store currently holds
    };

    // Cached icon HTML (avoids re-rendering SVG per card)
    let ICON_EXPAND_HTML = "";
    let ICON_COLLAPSE_HTML = "";

    // ==================== PRIORITY CONFIG ====================

    const PRIORITY_ORDER = {
        "Overdue": 0,
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
            restricted: true,
            // Set by the server only, once a task passes its deadline.
            hiddenOptions: ["Overdue"]
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

    const CARD_FIELDS = ["status", "type", "custom_utilization"];

    const optionsCache = {};

    const DROP_METHOD = "frappe.desk.doctype.kanban_board.kanban_board.update_order_for_single_card";
    const OPEN_METHOD = "frappe.desk.doctype.kanban_board.kanban_board.update_order";

    // The board's own card and column objects. Frappe's store keeps them
    // private; holding them lets a drop be recorded without redrawing the board.
    const cardObjects = new Map();
    const columnObjects = new Map();

    // Cards just moved. Board data fetched before the save still has them in
    // their old column, and a redraw from it would move them back.
    const recentMoves = new Map();
    const RECENT_MOVE_MS = 30 * 1000;

    // Work held back until the card in hand has been dropped.
    const afterDrag = [];

    // ==================== UTILITIES ====================

    function debounce(fn, delay) {
        let timeoutId;
        return function(...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function isDragging() {
        return !!window.Sortable?.dragged;
    }

    function runAfterDrag() {
        // Sortable ends the drag on this same event, and queues the drop's own
        // work while doing so, so look once it has finished.
        setTimeout(() => {
            if (!isDragging()) afterDrag.splice(0).forEach(fn => fn());
        }, 0);
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
            if (opts.method === DROP_METHOD && isKanbanView()) {
                return saveDroppedCard(opts);
            }
            if (opts.method === OPEN_METHOD && isKanbanView()) {
                return saveOpeningOrder(opts);
            }

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

    // ==================== DROP WITHOUT REDRAW ====================

    // Frappe freezes the screen on a drop and, once the server answers, redraws
    // every column and card on the board. Here the card stays where it was
    // dropped and is saved in the background; when the server agrees, only that
    // card and its new column are updated. If the save fails, the card goes back
    // to the column it came from and the error is shown, as before.
    function saveDroppedCard(opts) {
        // Frappe froze the screen just before calling; let the person carry on.
        frappe.dom.unfreeze();

        const { docname, from_colname, to_colname } = opts.args;
        // Returned in place of the request, so that Frappe's failure handler,
        // which redraws the whole board, never runs.
        const handled = $.Deferred().resolve().promise();

        // Columns are sorted by priority, so there is nothing to save.
        if (from_colname === to_colname) {
            reorderColumnByPriority(findColumn(to_colname));
            return handled;
        }

        recentMoves.set(docname, { column: to_colname, saving: true });
        findCard(docname).addClass("kanban-card-saving");

        if (!frappe.is_online()) {
            // frappe.call only warns about the connection, and never answers.
            state.originalFrappeCall.call(frappe, opts);
            restoreDroppedCard(docname, from_colname);
            return handled;
        }

        state.originalFrappeCall.call(frappe, Object.assign({}, opts, {
            callback: function(r) {
                if (r.exc) {
                    restoreDroppedCard(docname, from_colname);
                    return;
                }
                settleDroppedCard(docname, to_colname, r.message);
            }
        })).fail(() => restoreDroppedCard(docname, from_colname));

        return handled;
    }

    function settleDroppedCard(docname, colname, board) {
        // What Frappe's handler records, minus the redraw: the card's column,
        // and the columns' order (re-sorted by priority on the server).
        recordCardColumn(docname, colname);
        (board?.columns || []).forEach(col => {
            const column = columnObjects.get(col.column_name);
            if (column) column.order = col.order;
        });

        const $card = placeCard(docname, colname);

        const fieldname = cur_list?.board?.field_name || "status";
        const $field = $card.find(`[data-fieldname="${fieldname}"]`);
        if ($field.length) {
            $field.attr("data-current-value", colname);
            updateFieldDisplay($field, "status", colname);
        }
    }

    function restoreDroppedCard(docname, colname) {
        recentMoves.delete(docname);
        placeCard(docname, colname);
    }

    function placeCard(docname, colname) {
        const $card = findCard(docname).removeClass("kanban-card-saving");
        const $column = findColumn(colname);
        const $cards = $column.find(".kanban-cards");
        if (!$card.length || !$cards.length) return $card;

        if (!$.contains($cards[0], $card[0])) {
            $card.appendTo($cards);
        }
        reorderColumnByPriority($column, $card[0]);
        return $card;
    }

    function recordCardColumn(docname, colname) {
        recentMoves.set(docname, { column: colname, at: Date.now() });

        const card = cardObjects.get(docname);
        if (!card) return;
        // Changing a card in place does not set off Frappe's store watchers.
        card.column = colname;
        if (card.doc) card.doc[cur_list?.board?.field_name || "status"] = colname;
    }

    function findCard(docname) {
        const $wrapper = getKanbanWrapper() || $(document);
        // Not the ghost Sortable keeps following the pointer during a drag.
        return $wrapper.find(`.kanban-card-wrapper[data-name="${CSS.escape(encodeURIComponent(docname))}"]:not(.sortable-fallback)`);
    }

    // Within this board only: Frappe keeps other boards' pages in the DOM, and
    // jQuery copies a card appended to more than one column.
    function findColumn(colname) {
        const $wrapper = getKanbanWrapper() || $(document);
        return $wrapper.find(`.kanban-column[data-column-value="${CSS.escape(colname)}"]`);
    }

    // Opening a board, Frappe asks the server for the column order and then
    // draws the whole board a second time with it, or a third if the request
    // fails. Sorting the cards already on screen is enough.
    function saveOpeningOrder(opts) {
        state.originalFrappeCall.call(frappe, Object.assign({}, opts, {
            callback: r => sortColumnsByOrder(r.message?.[0])
        }));
        return $.Deferred().resolve().promise();
    }

    function sortColumnsByOrder(board) {
        if (isDragging()) {
            afterDrag.push(() => sortColumnsByOrder(board));
            return;
        }

        (board?.columns || []).forEach(col => {
            const column = columnObjects.get(col.column_name);
            if (!column || column.order === col.order) return;
            column.order = col.order;

            const rank = new Map(
                JSON.parse(col.order || "[]").map((name, i) => [encodeURIComponent(name), i])
            );
            const $cards = findColumn(col.column_name).find(".kanban-cards");
            // Cards the order doesn't list yet go first, as Frappe draws them.
            $cards.append($cards.children(".kanban-card-wrapper").toArray().sort(
                (a, b) => (rank.get(a.dataset.name) ?? -1) - (rank.get(b.dataset.name) ?? -1)
            ));
        });
    }

    // ==================== BOARD REDRAWS ====================

    // Frappe refreshes every list each 5 minutes, whatever the person is doing.
    // On a board each refresh empties the page and builds it from scratch, adding
    // store watchers that are never released: every one redraws the whole board
    // on the next refresh, so the work grows the longer the page stays open, until
    // the tab hangs. A card in hand at that moment stays on the page next to its
    // redrawn self, and can land in a column that no longer exists.
    //
    // Here a refresh only redraws the cards, only if the data changed, and waits
    // for a drag to end. The first draw, and coming back from another board
    // (Frappe's store holds one board at a time), still go through Frappe's.
    function patchBoardRender() {
        const proto = frappe.views?.KanbanView?.prototype;
        if (!proto || state.renderPatched) return;
        state.renderPatched = true;

        const render = proto.render;
        proto.render = function() {
            if (this.doctype !== TARGET_DOCTYPE) return render.apply(this, arguments);

            if (isDragging()) {
                afterDrag.push(() => this.render());
                return;
            }

            this.board.fields = [...CARD_FIELDS];
            keepRecentMoves(this);

            const data = JSON.stringify(this.data);
            const shown = this.kanban
                && state.shownBoard === this
                && this.$result.find(".kanban").length;

            if (!shown) {
                state.shownBoard = this;
                render.apply(this, arguments);
            } else if (data !== this.shownData) {
                const positions = captureScrollPositions();
                this.kanban.update(this.data);
                setTimeout(() => restoreScrollPositions(positions), 0);
            }
            this.shownData = data;
        };

        // Frappe's get_fields() adds the board's field again on every call. The
        // request then never looks the same as the last one, which defeats the
        // list's 3-second refresh throttle, and it keeps growing.
        const getFields = proto.get_fields;
        proto.get_fields = function() {
            const count = this.fields.length;
            const fields = getFields.apply(this, arguments);
            if (this.doctype === TARGET_DOCTYPE) this.fields.length = count;
            return fields;
        };
    }

    function keepRecentMoves(view) {
        const now = Date.now();
        recentMoves.forEach((move, name) => {
            if (!move.saving && now - move.at > RECENT_MOVE_MS) recentMoves.delete(name);
        });
        if (!recentMoves.size) return;

        view.data.forEach(row => {
            const move = recentMoves.get(row.name);
            if (move) row[view.board.field_name] = move.column;
        });
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
            options = options.filter(opt => !(config.hiddenOptions || []).includes(opt.value));
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


    // ==================== BOARD FIELDS NORMALIZATION ====================

    // Reverse lookup: fieldname -> FIELD_CONFIG key (built once)
    const FIELDNAME_TO_TYPE = Object.fromEntries(
        Object.entries(FIELD_CONFIGS).map(([key, cfg]) => [cfg.fieldname, key])
    );

    function normalizeBoardFields() {
        const board = cur_list?.board;
        if (!board?.fields) return;
        if (state.boardFieldsNormalized === board.name) return;

        board.fields = board.fields.map(f => f === "progress" ? "custom_utilization" : f);
        state.boardFieldsNormalized = board.name;
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

            const makeColumn = frappe.views.KanbanBoardColumn;
            if (typeof makeColumn === "function") {
                frappe.views.KanbanBoardColumn = function(column) {
                    columnObjects.set(column.title, column);
                    return makeColumn.apply(this, arguments);
                };
            }

            frappe.views.KanbanBoardCard = function(card, wrapper) {
                var self = {};

                function init() {
                    if (!card) return;
                    // Every column Frappe draws registers a store watcher that
                    // re-renders its cards and is never released (fixed upstream
                    // after 15.91), so replaced columns keep drawing into their
                    // removed DOM on every refresh. Skip those.
                    if (!wrapper?.[0]?.isConnected) return;
                    cardObjects.set(card.name, card);
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
                    // Read by reorderColumnByPriority, as priority is not shown on the card.
                    self.$card.attr("data-priority", card.doc?.priority || "");
                    if (recentMoves.get(card.name)?.saving) {
                        self.$card.addClass("kanban-card-saving");
                    }

                    // Bake in the collapse toggle button (no per-card listener needed; delegated)
                    self.$card.find(".kanban-card").append(
                        `<button class="kanban-toggle-btn" title="Toggle details">${ICON_EXPAND_HTML}</button>`
                    );

                    if (!frappe.model.can_write(card.doctype)) {
                        self.$card.find(".kanban-card-body").css("cursor", "default");
                    }
                }

                function get_doc_content(card) {
                    // Cache docfield_map lookup once per card (not per field)
                    const docfields = frappe.meta.docfield_map[card.doctype] || {};
                    const showLabels = cur_list.board.show_labels;
                    const docname = card.name;
                    let fields = [];

                    for (let field_name of cur_list.board.fields) {
                        let field = docfields[field_name] || frappe.model.get_std_field(field_name);
                        let label = showLabels
                            ? `<span>${__(field.label, null, field.parent)}: </span>`
                            : "";
                        let value = frappe.format(card.doc[field_name], field);

                        // Pinned fields stay visible when the card is collapsed
                        const isTaskType = field.fieldtype === "Link" && field.options === "Task Type";
                        const isUtilization = field_name === "custom_utilization";
                        const pinnedClass = (isTaskType || isUtilization) ? " kanban-field-pinned" : "";

                        // Bake inline-edit data attrs directly into the template
                        const fieldType = FIELDNAME_TO_TYPE[field_name];
                        let editableAttrs = "";
                        let editableClass = "";
                        if (fieldType && canEditField(fieldType)) {
                            const cfg = FIELD_CONFIGS[fieldType];
                            const rawVal = card.doc[field_name];
                            const currentValue = (rawVal === null || rawVal === undefined) ? "" : rawVal;
                            editableClass = " kanban-inline-editable";
                            editableAttrs =
                                ` data-field-type="${fieldType}"` +
                                ` data-docname="${frappe.utils.escape_html(docname)}"` +
                                ` data-current-value="${frappe.utils.escape_html(String(currentValue))}"` +
                                ` title="Click to edit ${cfg.label}"`;
                        }

                        fields.push(
                            `<div class="text-muted text-truncate${pinnedClass}${editableClass}" data-fieldname="${field_name}"${editableAttrs}>${label}<span>${value}</span></div>`
                        );
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
    patchBoardRender();

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
                    recordCardColumn(docname, newValue);
                    moveCardToColumn($field.closest(".kanban-card-wrapper"), newValue);
                }

                if (config.fieldname === "priority") {
                    $field.closest(".kanban-card-wrapper").attr("data-priority", newValue);
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

        const $targetColumn = findColumn(newStatus);
        if (!$targetColumn.length) return;

        const $currentColumn = $card.closest(".kanban-column");
        if ($currentColumn.attr("data-column-value") === newStatus) return;

        const $targetCards = $targetColumn.find(".kanban-cards");
        if (!$targetCards.length) return;

        $card.detach().appendTo($targetCards);
        updateColumnCount($currentColumn, -1);
        updateColumnCount($targetColumn, 1);
        reorderColumnByPriority($targetColumn, $card[0]);
    }

    function reorderColumnByPriority($column, movedCard = null) {
        if (!$column?.length) return;

        // Re-inserting cards would pull the one in hand along with them.
        if (isDragging()) {
            afterDrag.push(() => reorderColumnByPriority($column, movedCard));
            return;
        }

        const $cardsContainer = $column.find(".kanban-cards");
        if (!$cardsContainer.length) return;

        const cards = $cardsContainer.find(".kanban-card-wrapper").toArray();
        if (cards.length < 2) return;

        // Pre-extract priorities: from the priority field when the board shows
        // it (it is the live value after an inline edit), else from the card.
        const cardPriorities = new Map();
        cards.forEach(card => {
            const $priorityField = $(card).find('[data-fieldname="priority"]');
            const priority = ($priorityField.length
                ? $priorityField.attr('data-current-value')
                : card.dataset.priority) || '';
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

        const fragment = document.createDocumentFragment();
        cards.forEach(card => fragment.appendChild(card));
        $cardsContainer[0].appendChild(fragment);
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
            cur_list.board.fields = [...CARD_FIELDS];
        }
        normalizeBoardFields();
        const boardName = board?.name;

        if (!boardName || state.appliedBoardFilter === boardName) return;
        if (!board?.filters) return;

        const filters = typeof board.filters === "string"
            ? JSON.parse(board.filters)
            : board.filters;

        if (!filters?.length) return;

        state.appliedBoardFilter = boardName;

        // filters.push([TARGET_DOCTYPE, "status", "!=", "Closed"]);

        // Clearing and re-adding reloads the whole board, so leave it alone when
        // it already shows exactly the board's filters.
        const wanted = filters.map(f => [f[0], f[1], f[2], f[3]]);
        const key = list => list.map(f => JSON.stringify(f.slice(0, 4))).sort().join();
        if (key(cur_list.filter_area.get()) === key(wanted)) return;

        cur_list.filter_area.clear();
        cur_list.filter_area.add(wanted);
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
                if (cur_list?.$result?.hasClass('loading')) {
                    state.pendingRouteTimeout = setTimeout(onRouteChange, 100);
                    return;
                }

                applyBoardFilters();
                patchFrappeCallForScrollPreservation();
            } else {
                state.appliedBoardFilter = null;
                state.boardFieldsNormalized = null;
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
        if (state.themeObserver) {
            state.themeObserver.disconnect();
            state.themeObserver = null;
        }
        if (state.pendingRouteTimeout) {
            clearTimeout(state.pendingRouteTimeout);
            state.pendingRouteTimeout = null;
        }

        unpatchFrappeCall();

        Object.keys(optionsCache).forEach(key => delete optionsCache[key]);

        $(document).off("click.kanbanInlineEdit");
        $(document).off("click.kanbanToggle");
        $(document).off("click.kanbanCardExpand");
        $(document).off("page-change.kanbanCustom");
        state.routeListenerAttached = false;
        state.initialized = false;
        state.kanbanCardOverridden = false;
        state.boardFieldsNormalized = null;
    }
    
    // Expose cleanup for debugging/testing
    window.cleanupKanbanCustomizations = cleanup;

    // ==================== INITIALIZATION ====================

    function init() {
        if (state.initialized) return;
        state.initialized = true;

        initPermissions();
        setupThemeListener();
        patchFrappeCallForScrollPreservation();
        patchBoardRender();

        ["pointerup", "pointercancel", "mouseup", "touchend", "touchcancel"].forEach(event => {
            document.addEventListener(event, runAfterDrag);
        });

        // Cache icon HTML once (avoid re-rendering SVG per card)
        ICON_EXPAND_HTML = frappe.utils.icon("expand", "sm");
        ICON_COLLAPSE_HTML = frappe.utils.icon("collapse", "sm");

        // Set up route listener once
        if (!state.routeListenerAttached) {
            state.routeListenerAttached = true;

            $(document).on("page-change.kanbanCustom", onRouteChange);

            state.pendingRouteTimeout = setTimeout(() => {
                state.pendingRouteTimeout = null;
                if (isKanbanView()) {
                    applyBoardFilters();
                }
            }, 200);
        }

        // Delegated toggle button click (replaces per-card listener)
        $(document).off("click.kanbanToggle").on("click.kanbanToggle", ".kanban-toggle-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            const $card = $(this).closest(".kanban-card");
            const expanded = $card.toggleClass("expanded").hasClass("expanded");
            this.innerHTML = expanded ? ICON_COLLAPSE_HTML : ICON_EXPAND_HTML;
        });

        // Delegated expand-on-card-click (skips links, inline edits, and the toggle itself)
        $(document).off("click.kanbanCardExpand").on("click.kanbanCardExpand", ".kanban-card", function(e) {
            if (e.target.closest("a")) return;
            if (e.target.closest(".kanban-toggle-btn")) return;
            if (e.target.closest(".kanban-inline-editable")) return;
            if (this.classList.contains("expanded")) return;
            e.preventDefault();
            e.stopPropagation();
            this.classList.add("expanded");
            const btn = this.querySelector(".kanban-toggle-btn");
            if (btn) btn.innerHTML = ICON_COLLAPSE_HTML;
        });

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

    document.addEventListener("click", function(e) {
        const target = e.target.closest(".filter-button, .filter-x-button");
        if (!target) return;
        if (!isKanbanView()) return;

        // Might need to change this to the manager roles in site config later on
        const isSystemManager = frappe.user_roles.includes("System Manager");

        if (!isSystemManager) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
        }
    }, true);

    // Start initialization when DOM is ready
    $(document).ready(init);

})();