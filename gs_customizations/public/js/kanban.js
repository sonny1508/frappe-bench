$(document).ready(function() {
    
    function replaceAvatarsWithNames($assignmentsContainer) {
        const $avatarGroup = $assignmentsContainer.find('.avatar-group');
        if ($avatarGroup.length === 0 || $avatarGroup.data('names-replaced')) return;
        
        // Mark as processed to avoid re-processing
        $avatarGroup.data('names-replaced', true);
        
        // Extract names from title attributes
        const names = [];
        $avatarGroup.find('.avatar[title]').each(function() {
            const title = $(this).attr('title');
            if (title) names.push(title);
        });
        
        if (names.length === 0) return;
        
        // Create names container
        const $namesContainer = $('<div class="kanban-assignee-names"></div>');
        names.forEach(name => {
            $namesContainer.append(
                `<span class="kanban-assignee-tag">${frappe.utils.escape_html(name)}</span>`
            );
        });
        
        // Preserve the "add" button
        const $addBtn = $avatarGroup.find('.avatar-action').closest('.avatar').clone(true);
        
        // Replace content
        $avatarGroup.removeClass('overlap').empty().append($namesContainer);
        if ($addBtn.length) {
            $avatarGroup.append($addBtn);
        }
    }
    
    // MutationObserver to catch dynamically added cards
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType !== 1) return;
                
                const $node = $(node);
                
                // Direct kanban-card-wrapper
                if ($node.hasClass('kanban-card-wrapper')) {
                    replaceAvatarsWithNames($node.find('.kanban-assignments'));
                }
                
                // Or contains kanban elements
                $node.find('.kanban-assignments').each(function() {
                    replaceAvatarsWithNames($(this));
                });
            });
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    // Process any existing cards on page load
    $(document).on('page-change', function() {
        setTimeout(processExistingCards, 300);
    });
    
    function processExistingCards() {
        $('.kanban-assignments').each(function() {
            replaceAvatarsWithNames($(this));
        });
    }
    
    // Initial run
    setTimeout(processExistingCards, 500);
});