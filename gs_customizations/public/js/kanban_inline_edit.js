/**
 * Kanban Inline Edit - Multi-Field Support
 * 
 * Allows editing Priority, Status, Type, and Progress fields directly on Kanban cards
 * without opening the full document form.
 * 
 * Features:
 * - Dynamic option loading from DocType meta and linked DocTypes
 * - Dark/Light theme support
 * - Auto-save on change
 */

(function() {
    "use strict";

    const DOCTYPE = "Task";

    // ========== FIELD CONFIGURATIONS ==========

    const FIELD_CONFIGS = {
        priority: {
            fieldname: "priority",
            label: "Priority",
            detectPatterns: ["Priority"],
            optionType: "select"
        },
        status: {
            fieldname: "status",
            label: "Status",
            detectPatterns: ["Status"],
            optionType: "select"
        },
        type: {
            fieldname: "type",
            label: "Type",
            detectPatterns: ["Type"],
            optionType: "link",
            linkDoctype: "Task Type"
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
            isNumeric: true
        }
    };

    // Cache for dynamically loaded options
    const optionsCache = {};

    // Track which cards we've already enhanced to avoid duplicates
    const enhancedCards = new WeakSet();

    // ========== OPTION LOADING ==========

    /**
     * Load options for a field based on its configuration
     * Returns a Promise that resolves to an array of {value, display} objects
     */
    async function loadFieldOptions(fieldType) {
        const config = FIELD_CONFIGS[fieldType];

        // Return cached options if available
        if (optionsCache[fieldType]) {
            return optionsCache[fieldType];
        }

        let options = [];

        if (config.optionType === "static") {
            // Static options defined in config (e.g., progress)
            options = config.options;
        } else if (config.optionType === "select") {
            // Select field - get options from DocType meta
            options = await loadSelectOptions(config.fieldname);
        } else if (config.optionType === "link") {
            // Link field - get options from linked DocType
            options = await loadLinkOptions(config.linkDoctype);
        }

        // Cache the options
        optionsCache[fieldType] = options;
        return options;
    }

    /**
     * Load options from a Select field's meta
     */
    async function loadSelectOptions(fieldname) {
        return new Promise((resolve, reject) => {
            // Ensure meta is loaded
            frappe.model.with_doctype(DOCTYPE, function() {
                const field = frappe.meta.get_field(DOCTYPE, fieldname);

                if (!field || !field.options) {
                    reject(new Error(`Could not load options for field: ${fieldname}`));
                    return;
                }

                // Parse options (newline separated string)
                const optionValues = field.options.split("\n").filter(opt => opt.trim());
                const options = optionValues.map(value => ({
                    value: value.trim(),
                    display: value.trim()
                }));

                resolve(options);
            });
        });
    }

    /**
     * Load options from a linked DocType
     */
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

                    const options = r.message.map(doc => ({
                        value: doc.name,
                        display: doc.name
                    }));

                    resolve(options);
                },
                error: function() {
                    reject(new Error(`Failed to fetch from: ${linkDoctype}`));
                }
            });
        });
    }

    /**
     * Clear options cache (useful if options change)
     */
    function clearOptionsCache(fieldType) {
        if (fieldType) {
            delete optionsCache[fieldType];
        } else {
            Object.keys(optionsCache).forEach(key => delete optionsCache[key]);
        }
    }

    // Expose cache clearing function globally for manual refresh if needed
    window.clearKanbanOptionsCache = clearOptionsCache;

    // ========== THEME DETECTION ==========

    function isDarkTheme() {
        return document.documentElement.getAttribute("data-theme") === "dark";
    }

    // ========== FIELD DETECTION ==========

    /**
     * Detect which field type a div contains based on its text content
     */
    function detectFieldType($div) {
        const text = $div.text();

        for (const [key, config] of Object.entries(FIELD_CONFIGS)) {
            // Check if any detection pattern matches
            const patternMatch = config.detectPatterns.some(pattern => text.includes(pattern));
            if (patternMatch) {
                return key;
            }
        }

        return null;
    }

    /**
     * Extract current value from field text
     */
    function extractCurrentValue($div, fieldType) {
        const config = FIELD_CONFIGS[fieldType];
        const text = $div.text();

        if (config.isNumeric) {
            // Extract number from text like "% Progress: 25,000%" or "Progress: 50%"
            // Handle comma as decimal separator (European format)
            const match = text.match(/(\d+)[,.]?\d*/);
            if (match) {
                const num = parseInt(match[1], 10);
                // Round to nearest 10
                return Math.round(num / 10) * 10;
            }
            return 0;
        } else {
            // For select/link fields, extract value after the colon
            // Format is typically "Label: Value"
            const colonIndex = text.indexOf(":");
            if (colonIndex !== -1) {
                return text.substring(colonIndex + 1).trim();
            }
            return text.trim();
        }
    }

    // ========== CARD ENHANCEMENT ==========

    /**
     * Enhance a single kanban card with inline editing for all supported fields
     */
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
     * Scan and enhance all kanban cards on the page
     */
    function enhanceAllCards() {
        $(".kanban-card-wrapper").each(function() {
            enhanceCard($(this));
        });
    }

    // ========== MUTATION OBSERVER ==========

    function setupObserver() {
        const observer = new MutationObserver(function(mutations) {
            let shouldEnhance = false;

            for (const mutation of mutations) {
                if (mutation.addedNodes.length) {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            if ($(node).hasClass("kanban-card-wrapper") ||
                                $(node).find(".kanban-card-wrapper").length) {
                                shouldEnhance = true;
                                break;
                            }
                        }
                    }
                }
                if (shouldEnhance) break;
            }

            if (shouldEnhance) {
                setTimeout(enhanceAllCards, 50);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        return observer;
    }

    // ========== DROPDOWN UI ==========

    /**
     * Show dropdown for field selection
     */
    async function showDropdown($field, fieldType, docname, currentValue) {
        $(".kanban-inline-dropdown").remove();

        // Load options dynamically
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

        const config = FIELD_CONFIGS[fieldType];

        const optionsHtml = options.map(opt => {
            const value = opt.value;
            const displayText = opt.display || opt.value;
            const isSelected = String(value) === String(currentValue) ? "selected" : "";

            return `
                <div class="kanban-inline-option ${isSelected}" data-value="${value}">
                    <span class="kanban-inline-label">${displayText}</span>
                </div>
            `;
        }).join("");

        const $dropdown = $(`<div class="kanban-inline-dropdown" data-field-type="${fieldType}">${optionsHtml}</div>`);

        // Position dropdown
        const rect = $field[0].getBoundingClientRect();
        let top = rect.bottom + 4;
        let left = rect.left;

        // Append first to get dimensions
        $("body").append($dropdown);

        // Adjust if dropdown would go off screen
        const dropdownRect = $dropdown[0].getBoundingClientRect();
        if (top + dropdownRect.height > window.innerHeight) {
            top = rect.top - dropdownRect.height - 4;
        }
        if (left + dropdownRect.width > window.innerWidth) {
            left = window.innerWidth - dropdownRect.width - 10;
        }

        $dropdown.css({ "top": top + "px", "left": left + "px" });

        // Handle selection
        $dropdown.on("click", ".kanban-inline-option", function(e) {
            e.stopPropagation();
            e.preventDefault();

            const newValue = $(this).attr("data-value");
            $dropdown.remove();

            if (String(newValue) !== String(currentValue)) {
                saveValue(fieldType, docname, newValue, $field);
            }
        });

        // Close on outside click
        setTimeout(() => {
            $(document).one("click.kanban-dropdown", function() {
                $dropdown.remove();
            });
        }, 10);
    }

    // ========== SAVE FUNCTIONALITY ==========

    /**
     * Save the new value to the server
     */
    function saveValue(fieldType, docname, newValue, $field) {
        const config = FIELD_CONFIGS[fieldType];

        // Convert to proper type for saving
        let saveValue = newValue;
        if (config.isNumeric) {
            saveValue = parseFloat(newValue);
        }

        // Visual feedback
        $field.addClass("kanban-inline-saving");

        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: DOCTYPE,
                name: docname,
                fieldname: config.fieldname,
                value: saveValue
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

                // Update the stored current value
                $field.attr("data-current-value", newValue);

                // Update display text
                updateFieldDisplay($field, fieldType, newValue);

                frappe.show_alert({
                    message: __("{0} updated to {1}", [config.label, getDisplayValue(fieldType, newValue)]),
                    indicator: "green"
                }, 3);

                if (config.fieldname === "status") {
                    moveCardToColumn($field.closest(".kanban-card-wrapper"), newValue);
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

    /**
     * Get display value for a field
     */
    function getDisplayValue(fieldType, value) {
        const config = FIELD_CONFIGS[fieldType];
        if (config.isNumeric && config.options) {
            const opt = config.options.find(o => o.value === parseInt(value, 10));
            return opt ? opt.display : value + "%";
        }
        return value;
    }

    /**
     * Update the visual display of the field after save
     */
    function updateFieldDisplay($field, fieldType, newValue) {
        const displayValue = getDisplayValue(fieldType, newValue);

        // Try to find value span (usually the last one or one after a label)
        const $spans = $field.find("span");

        if ($spans.length >= 2) {
            // Format like "Label: Value" - update last span
            $spans.last().text(displayValue);
        } else if ($spans.length === 1) {
            $spans.text(displayValue);
        } else {
            // No spans - try to preserve label if present
            const currentText = $field.text();
            const labelMatch = currentText.match(/^([^:]+:\s*)/);
            if (labelMatch) {
                $field.text(labelMatch[1] + displayValue);
            } else {
                $field.text(displayValue);
            }
        }
    }

    /**
     * Move a card to the appropriate column based on new status value
     * Mimics drag-and-drop behavior without full board refresh
     */
    function moveCardToColumn($card, newStatus) {
        if (!$card.length) return;
        
        // Find the target column by status value
        const $targetColumn = $(`.kanban-column[data-column-value="${newStatus}"]`);
        
        if (!$targetColumn.length) return;
        
        const $currentColumn = $card.closest(".kanban-column");
        
        // Only move if actually changing columns
        if ($currentColumn.attr("data-column-value") === newStatus) return;
        
        // Find the cards container within the column
        const $targetCards = $targetColumn.find(".kanban-cards");
        
        if (!$targetCards.length) return;
        
        // Detach and append to new column
        $card.detach().appendTo($targetCards);
        
        // Update column card counts if they exist
        updateColumnCount($currentColumn, -1);
        updateColumnCount($targetColumn, 1);
    }

    /**
     * Update the card count display in a column header
     */
    function updateColumnCount($column, delta) {
        const $count = $column.find(".column-card-count, .kanban-column-count");
        if ($count.length) {
            const current = parseInt($count.text(), 10) || 0;
            $count.text(current + delta);
        }
    }

    // ========== THEME CHANGE LISTENER ==========

    function setupThemeListener() {
        const observer = new MutationObserver(function(mutations) {
            for (const mutation of mutations) {
                if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                    // Theme changed - close any open dropdowns
                    $(".kanban-inline-dropdown").remove();
                }
            }
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme"]
        });
    }

    // ========== DRAG DROP SYNC ==========

    function setupDragDropSync() {
        const originalUnfreeze = frappe.dom.unfreeze;
        
        frappe.dom.unfreeze = function() {
            originalUnfreeze.apply(this, arguments);
            // Sync card displays after drag-drop completes
            setTimeout(syncAllCardsWithColumns, 100);
        };
    }

    function syncAllCardsWithColumns() {
        $('.kanban-card-wrapper').each(function() {
            const $card = $(this);
            const $column = $card.closest('.kanban-column');
            const columnStatus = $column.attr('data-column-value');
            
            if (!columnStatus) return;
            
            const $statusField = $card.find('[data-fieldname="status"]');
            if ($statusField.length && $statusField.attr('data-current-value') !== columnStatus) {
                $statusField.attr('data-current-value', columnStatus);
                updateFieldDisplay($statusField, 'status', columnStatus);
            }
        });
    }

    // ========== INITIALIZATION ==========

    function init() {
        setupObserver();
        setupThemeListener();
        enhanceAllCards();
        setupDragDropSync();

        // Enhance on SPA navigation
        $(document).on("page-change", enhanceAllCards);

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

        // console.log("Kanban inline edit (multi-field) initialized");
    }

    $(document).ready(init);

})();