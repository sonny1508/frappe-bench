/**
 * Kanban Inline Edit - Multi-Field Support
 * 
 * Allows editing Priority, Status, and Progress fields directly on Kanban cards
 * without opening the full document form.
 * 
 * Features:
 * - Priority: Urgent, High, Medium, Low, Support
 * - Status: Open, Working, QA Pending, QA Reviewing, QA Feedback, Delivered, Client Feedback, Overdue, Completed
 * - Progress: 0% to 100% in 10% increments
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
            options: [
                { value: "Urgent", color: "red" },
                { value: "High", color: "orange" },
                { value: "Medium", color: "blue" },
                { value: "Low", color: "gray" },
                { value: "Support", color: "green" }
            ]
        },
        status: {
            fieldname: "status",
            label: "Status",
            detectPatterns: ["Status"],
            options: [
                { value: "Open", color: "blue" },
                { value: "Working", color: "orange" },
                { value: "QA Pending", color: "purple" },
                { value: "QA Reviewing", color: "cyan" },
                { value: "QA Feedback", color: "yellow" },
                { value: "Delivered", color: "green" },
                { value: "Client Feedback", color: "pink" },
                { value: "Overdue", color: "red" },
                { value: "Completed", color: "darkgreen" }
            ]
        },
        type: {
            fieldname: "type",
            label: "Type",
            detectPatterns: ["Type"],
            options: [
                {value: "Step 01"},
                {value: "Step 02"},
            ]
        },
        progress: {
            fieldname: "progress",
            label: "Progress",
            detectPatterns: ["Progress", "%"],
            options: [
                { value: 0, display: "0%", color: "gray" },
                { value: 10, display: "10%", color: "lightblue" },
                { value: 20, display: "20%", color: "lightblue" },
                { value: 30, display: "30%", color: "blue" },
                { value: 40, display: "40%", color: "blue" },
                { value: 50, display: "50%", color: "blue" },
                { value: 60, display: "60%", color: "teal" },
                { value: 70, display: "70%", color: "teal" },
                { value: 80, display: "80%", color: "green" },
                { value: 90, display: "90%", color: "green" },
                { value: 100, display: "100%", color: "darkgreen" }
            ],
            isNumeric: true
        }
    };

    // Color mappings for indicator pills (light theme)
    const COLOR_MAP_LIGHT = {
        red: "#e74c3c",
        orange: "#e67e22",
        yellow: "#f1c40f",
        green: "#27ae60",
        darkgreen: "#1e8449",
        blue: "#3498db",
        lightblue: "#85c1e9",
        purple: "#9b59b6",
        cyan: "#17a2b8",
        pink: "#e91e63",
        gray: "#95a5a6",
        teal: "#16a085"
    };

    // Color mappings for indicator pills (dark theme - slightly brighter)
    const COLOR_MAP_DARK = {
        red: "#ff6b6b",
        orange: "#ffa94d",
        yellow: "#ffd43b",
        green: "#51cf66",
        darkgreen: "#40c057",
        blue: "#74c0fc",
        lightblue: "#a5d8ff",
        purple: "#da77f2",
        cyan: "#66d9e8",
        pink: "#f783ac",
        gray: "#adb5bd",
        teal: "#38d9a9"
    };

    // Track which cards we've already enhanced to avoid duplicates
    const enhancedCards = new WeakSet();

    // ========== THEME DETECTION ==========

    function isDarkTheme() {
        return document.documentElement.getAttribute("data-theme") === "dark";
    }

    function getColorMap() {
        return isDarkTheme() ? COLOR_MAP_DARK : COLOR_MAP_LIGHT;
    }

    function getThemeColors() {
        const dark = isDarkTheme();
        return {
            dropdownBg: dark ? "#1a1a2e" : "#ffffff",
            dropdownBorder: dark ? "#404040" : "#d1d8dd",
            dropdownShadow: dark ? "rgba(0,0,0,0.4)" : "rgba(0,0,0,0.15)",
            optionHover: dark ? "#2d2d44" : "#f4f5f6",
            optionSelected: dark ? "#1e3a5f" : "#e3f2fd",
            textColor: dark ? "#e0e0e0" : "#333333",
            editableHover: dark ? "#2d2d44" : "#f0f4f7"
        };
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
            if (!patternMatch) continue;

            // For priority and status, check if any option value is present
            if (!config.isNumeric) {
                const valueMatch = config.options.some(opt => text.includes(opt.value));
                if (valueMatch) return key;
            } else {
                // For numeric fields like progress, just pattern match is enough
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
            // Find matching option value
            for (const opt of config.options) {
                if (text.includes(opt.value)) {
                    return opt.value;
                }
            }
            return config.options[0].value;
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
    function showDropdown($field, fieldType, docname, currentValue) {
        $(".kanban-inline-dropdown").remove();

        const config = FIELD_CONFIGS[fieldType];
        const colorMap = getColorMap();
        const theme = getThemeColors();

        const optionsHtml = config.options.map(opt => {
            const value = opt.value;
            const displayText = opt.display || opt.value;
            const isSelected = String(value) === String(currentValue) ? "selected" : "";
            const colorHex = colorMap[opt.color] || opt.color;

            return `
                <div class="kanban-inline-option ${isSelected}" data-value="${value}">
                    <span class="kanban-inline-indicator" style="background-color: ${colorHex};"></span>
                    <span class="kanban-inline-label">${displayText}</span>
                </div>
            `;
        }).join("");

        const $dropdown = $(`<div class="kanban-inline-dropdown" data-field-type="${fieldType}">${optionsHtml}</div>`);

        // Apply theme-aware styles
        $dropdown.css({
            "position": "fixed",
            "z-index": "1060",
            "background": theme.dropdownBg,
            "border": `1px solid ${theme.dropdownBorder}`,
            "border-radius": "8px",
            "box-shadow": `0 4px 12px ${theme.dropdownShadow}`,
            "padding": "4px 0",
            "min-width": "140px",
            "max-height": "300px",
            "overflow-y": "auto"
        });

        $dropdown.find(".kanban-inline-option").css({
            "padding": "8px 12px",
            "cursor": "pointer",
            "display": "flex",
            "align-items": "center",
            "font-size": "13px",
            "color": theme.textColor
        });

        $dropdown.find(".kanban-inline-indicator").css({
            "display": "inline-block",
            "width": "10px",
            "height": "10px",
            "border-radius": "50%",
            "margin-right": "10px",
            "flex-shrink": "0"
        });

        $dropdown.find(".kanban-inline-option.selected").css({
            "background-color": theme.optionSelected,
            "font-weight": "500"
        });

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

        $dropdown.css({ "top": top, "left": left });

        // Hover effects
        $dropdown.find(".kanban-inline-option").hover(
            function() {
                if (!$(this).hasClass("selected")) {
                    $(this).css("background-color", theme.optionHover);
                }
            },
            function() {
                if (!$(this).hasClass("selected")) {
                    $(this).css("background-color", "transparent");
                }
            }
        );

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
        $field.css("opacity", "0.5");

        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: DOCTYPE,
                name: docname,
                fieldname: config.fieldname,
                value: saveValue
            },
            callback: function(r) {
                $field.css("opacity", "1");

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

                // Refresh the Kanban board to reflect changes (re-sort, move cards between columns)
                if (cur_list && cur_list.refresh) {
                    cur_list.refresh();
                }
            },
            error: function() {
                $field.css("opacity", "1");
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
        if (config.isNumeric) {
            const opt = config.options.find(o => o.value === parseInt(value, 10));
            return opt ? opt.display : value + "%";
        }
        return value;
    }

    /**
     * Update the visual display of the field after save
     */
    function updateFieldDisplay($field, fieldType, newValue) {
        const config = FIELD_CONFIGS[fieldType];
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

    // ========== STYLES ==========

    function injectStyles() {
        const css = `
            .kanban-inline-editable {
                cursor: pointer !important;
                border-radius: 4px;
                padding: 2px 6px;
                margin: -2px -6px;
                transition: background-color 0.15s ease;
            }

            /* Light theme hover */
            [data-theme="light"] .kanban-inline-editable:hover,
            :root:not([data-theme="dark"]) .kanban-inline-editable:hover {
                background-color: #f0f4f7;
            }

            /* Dark theme hover */
            [data-theme="dark"] .kanban-inline-editable:hover {
                background-color: #2d2d44;
            }

            .kanban-inline-dropdown {
                animation: kanban-dropdown-fade 0.15s ease;
            }

            @keyframes kanban-dropdown-fade {
                from { opacity: 0; transform: translateY(-4px); }
                to { opacity: 1; transform: translateY(0); }
            }

            /* Scrollbar styling for dropdown */
            .kanban-inline-dropdown::-webkit-scrollbar {
                width: 6px;
            }

            .kanban-inline-dropdown::-webkit-scrollbar-track {
                background: transparent;
            }

            .kanban-inline-dropdown::-webkit-scrollbar-thumb {
                background-color: #888;
                border-radius: 3px;
            }

            [data-theme="dark"] .kanban-inline-dropdown::-webkit-scrollbar-thumb {
                background-color: #555;
            }
        `;

        $("<style id='kanban-inline-edit-styles'>").text(css).appendTo("head");
    }

    // ========== THEME CHANGE LISTENER ==========

    function setupThemeListener() {
        // Watch for theme changes on document element
        const observer = new MutationObserver(function(mutations) {
            for (const mutation of mutations) {
                if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                    // Theme changed - close any open dropdowns (they'll reopen with new colors)
                    $(".kanban-inline-dropdown").remove();
                }
            }
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme"]
        });
    }

    // ========== INITIALIZATION ==========

    function init() {
        // Remove any existing styles (in case of reload)
        $("#kanban-inline-edit-styles").remove();

        injectStyles();
        setupObserver();
        setupThemeListener();
        enhanceAllCards();

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

        console.log("Kanban inline edit (multi-field) initialized");
    }

    $(document).ready(init);

})();