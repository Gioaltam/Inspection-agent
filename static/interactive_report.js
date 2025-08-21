// Global variables
let currentTab = 'overview';
let reportData = window.REPORT_DATA || {};
let allFindings = [];
let filteredFindings = [];
let allPhotos = [];
let filteredPhotos = [];

// Filter state
let filters = {
    search: '',
    severity: '',
    status: '',
    area: '',
    system: '',
    sort: 'severity-desc'
};

// Initialize the page when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeReport();
});

// Initialize report with data
function initializeReport() {
    if (!reportData) {
        console.error('No report data available');
        showErrorMessage('Unable to load report data. Please refresh the page.');
        return;
    }

    // Store all findings and photos
    allFindings = reportData.findings || [];
    allPhotos = reportData.photos || [];
    
    // Initialize findings with default data if needed
    allFindings = allFindings.map((finding, index) => ({
        ...finding,
        id: finding.id || `finding-${index}`,
        severity: finding.severity || 'informational',
        status: finding.status || 'open',
        area: finding.area || finding.location || 'General',
        system: finding.system || 'General',
        tags: finding.tags || [],
        updated: finding.updated || finding.created_at || new Date().toISOString()
    }));

    // Update overview statistics
    updateOverview();
    
    // Populate filter dropdowns
    populateFilterDropdowns();
    
    // Load and display findings
    applyFilters();
    
    // Load photos
    filterPhotos();
    
    // Load systems
    loadSystems();
    
    // Set up lazy loading for images
    setupLazyLoading();
}

// Update overview tab statistics
function updateOverview() {
    const totals = reportData.totals || {};
    const photos = reportData.photos || [];
    
    // Update stat cards with null checks
    const criticalElement = document.getElementById('critical-issues');
    const importantElement = document.getElementById('important-issues');
    const totalElement = document.getElementById('total-issues');
    const photoCountElement = document.getElementById('photo-count');
    
    if (criticalElement) criticalElement.textContent = totals.critical_issues || 0;
    if (importantElement) importantElement.textContent = totals.important_issues || 0;
    if (totalElement) totalElement.textContent = 
        (totals.critical_issues || 0) + (totals.important_issues || 0);
    if (photoCountElement) photoCountElement.textContent = photos.length;
    
    // Update property summary
    const summaryElement = document.getElementById('property-summary');
    if (reportData.property_info) {
        summaryElement.innerHTML = `
            <p><strong>Address:</strong> ${reportData.property_info.address || 'N/A'}</p>
            <p><strong>Type:</strong> ${reportData.property_info.type || 'Residential'}</p>
            <p><strong>Inspection Date:</strong> ${formatDate(reportData.inspection_date)}</p>
            <p><strong>Inspector:</strong> ${reportData.inspector || 'N/A'}</p>
        `;
    }
    
    // Update key findings
    const keyFindingsElement = document.getElementById('key-findings');
    const criticalFindings = allFindings
        .filter(f => f.severity === 'critical')
        .slice(0, 3);
    
    if (criticalFindings.length > 0) {
        keyFindingsElement.innerHTML = '<ul>' + 
            criticalFindings.map(f => `<li>${f.title || f.description}</li>`).join('') + 
            '</ul>';
    } else {
        keyFindingsElement.innerHTML = '<p>No critical issues found during inspection.</p>';
    }
}

// Populate filter dropdowns with unique values from findings
function populateFilterDropdowns() {
    // Get unique areas
    const areas = [...new Set(allFindings.map(f => f.area))].sort();
    const areaSelect = document.getElementById('area-filter');
    if (areaSelect) {
        areaSelect.innerHTML = '<option value="">All Areas</option>' +
            areas.map(area => `<option value="${area}">${area}</option>`).join('');
    }
    
    // Get unique systems
    const systems = [...new Set(allFindings.map(f => f.system))].sort();
    const systemSelect = document.getElementById('system-filter');
    if (systemSelect) {
        systemSelect.innerHTML = '<option value="">All Systems</option>' +
            systems.map(system => `<option value="${system}">${system}</option>`).join('');
    }
}

// Apply all filters and sort findings
function applyFilters() {
    // Get current filter values
    filters.search = document.getElementById('findings-search')?.value || '';
    filters.severity = document.getElementById('severity-filter')?.value || '';
    filters.status = document.getElementById('status-filter')?.value || '';
    filters.area = document.getElementById('area-filter')?.value || '';
    filters.system = document.getElementById('system-filter')?.value || '';
    filters.sort = document.getElementById('sort-filter')?.value || 'severity-desc';
    
    // Start with all findings
    filteredFindings = [...allFindings];
    
    // Apply search filter
    if (filters.search) {
        const searchLower = filters.search.toLowerCase();
        filteredFindings = filteredFindings.filter(f => 
            (f.title && f.title.toLowerCase().includes(searchLower)) ||
            (f.description && f.description.toLowerCase().includes(searchLower)) ||
            (f.area && f.area.toLowerCase().includes(searchLower)) ||
            (f.system && f.system.toLowerCase().includes(searchLower)) ||
            (f.tags && f.tags.some(tag => tag.toLowerCase().includes(searchLower)))
        );
    }
    
    // Apply severity filter
    if (filters.severity) {
        filteredFindings = filteredFindings.filter(f => f.severity === filters.severity);
    }
    
    // Apply status filter
    if (filters.status) {
        filteredFindings = filteredFindings.filter(f => f.status === filters.status);
    }
    
    // Apply area filter
    if (filters.area) {
        filteredFindings = filteredFindings.filter(f => f.area === filters.area);
    }
    
    // Apply system filter
    if (filters.system) {
        filteredFindings = filteredFindings.filter(f => f.system === filters.system);
    }
    
    // Sort findings
    sortFindings();
    
    // Render filtered findings
    renderFindings();
    
    // Update count
    updateFindingsCount();
}

// Sort findings based on selected criteria
function sortFindings() {
    const severityOrder = { critical: 3, important: 2, informational: 1 };
    
    switch (filters.sort) {
        case 'severity-desc':
            filteredFindings.sort((a, b) => 
                (severityOrder[b.severity] || 0) - (severityOrder[a.severity] || 0));
            break;
        case 'severity-asc':
            filteredFindings.sort((a, b) => 
                (severityOrder[a.severity] || 0) - (severityOrder[b.severity] || 0));
            break;
        case 'updated-desc':
            filteredFindings.sort((a, b) => 
                new Date(b.updated || 0) - new Date(a.updated || 0));
            break;
        case 'updated-asc':
            filteredFindings.sort((a, b) => 
                new Date(a.updated || 0) - new Date(b.updated || 0));
            break;
        case 'area-asc':
            filteredFindings.sort((a, b) => 
                (a.area || '').localeCompare(b.area || ''));
            break;
        case 'area-desc':
            filteredFindings.sort((a, b) => 
                (b.area || '').localeCompare(a.area || ''));
            break;
    }
}

// Render filtered findings to the page
function renderFindings() {
    const container = document.getElementById('findings-list');
    
    if (filteredFindings.length === 0) {
        container.innerHTML = '<p class="no-results">No findings match your filters.</p>';
        return;
    }
    
    container.innerHTML = filteredFindings.map(finding => createFindingCard(finding)).join('');
}

// Create HTML for a finding card
function createFindingCard(finding) {
    const severityClass = `severity-${finding.severity}`;
    const statusClass = `status-${finding.status}`;
    const photos = finding.photos || [];
    const isReadOnly = window.IS_READONLY || false;
    
    return `
        <div class="finding-item" data-severity="${finding.severity}" data-status="${finding.status}" data-finding-id="${finding.id}">
            <div class="finding-header">
                <div class="finding-title">${finding.title || 'Finding'}</div>
                <div class="finding-badges">
                    <span class="finding-severity ${severityClass}">${finding.severity}</span>
                    <span class="finding-status ${statusClass}" id="status-${finding.id}">${finding.status}</span>
                </div>
            </div>
            <div class="finding-description">${finding.description || ''}</div>
            <div class="finding-meta">
                ${finding.area ? `<span class="meta-item">📍 ${finding.area}</span>` : ''}
                ${finding.system ? `<span class="meta-item">⚙️ ${finding.system}</span>` : ''}
                ${finding.updated ? `<span class="meta-item">🕐 ${formatRelativeTime(finding.updated)}</span>` : ''}
            </div>
            ${finding.tags && finding.tags.length > 0 ? `
                <div class="finding-tags">
                    ${finding.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
            ` : ''}
            ${photos.length > 0 ? `
                <div class="finding-photos">
                    ${photos.map(photo => `
                        <img src="${photo.url || photo}" 
                             alt="${finding.title || 'Finding photo'}" 
                             class="finding-photo" 
                             loading="lazy"
                             decoding="async"
                             onclick="openPhotoModal('${photo.url || photo}', '${finding.title}')">
                    `).join('')}
                </div>
            ` : ''}
            ${!isReadOnly ? `
                <div class="finding-actions">
                    <select class="status-select" onchange="updateFindingStatus('${finding.id}', this.value)">
                        <option value="open" ${finding.status === 'open' ? 'selected' : ''}>Open</option>
                        <option value="resolved" ${finding.status === 'resolved' ? 'selected' : ''}>Resolved</option>
                        <option value="deferred" ${finding.status === 'deferred' ? 'selected' : ''}>Deferred</option>
                    </select>
                    <button class="btn-comment" onclick="addComment('${finding.id}')">Add Comment</button>
                </div>
            ` : ''}
            <div class="finding-comments" id="comments-${finding.id}">
                ${finding.comments && finding.comments.length > 0 ? 
                    finding.comments.map(comment => `
                        <div class="comment">
                            <div class="comment-author">${comment.author}</div>
                            <div class="comment-body">${comment.body}</div>
                            <div class="comment-date">${formatRelativeTime(comment.created_at)}</div>
                        </div>
                    `).join('') : ''
                }
            </div>
        </div>
    `;
}

// Update findings count display
function updateFindingsCount() {
    const countElement = document.getElementById('findings-count');
    const totalElement = document.getElementById('findings-total');
    
    if (countElement) countElement.textContent = filteredFindings.length;
    if (totalElement) totalElement.textContent = allFindings.length;
}

// Handle findings search input
function handleFindingsSearch() {
    applyFilters();
}

// Handle photos search
function handlePhotosSearch() {
    filterPhotos();
}

// Filter photos based on search
function filterPhotos() {
    const searchTerm = document.getElementById('photos-search')?.value || '';
    
    if (searchTerm) {
        const searchLower = searchTerm.toLowerCase();
        filteredPhotos = allPhotos.filter(photo => {
            const caption = photo.caption || photo.description || '';
            const tags = photo.tags || [];
            return caption.toLowerCase().includes(searchLower) ||
                   tags.some(tag => tag.toLowerCase().includes(searchLower));
        });
    } else {
        filteredPhotos = [...allPhotos];
    }
    
    renderPhotos();
    updatePhotosCount();
}

// Render filtered photos
function renderPhotos() {
    const container = document.getElementById('photos-grid');
    
    if (filteredPhotos.length === 0) {
        container.innerHTML = '<p class="no-results">No photos match your search.</p>';
        return;
    }
    
    container.innerHTML = filteredPhotos.map((photo, index) => `
        <div class="photo-item" onclick="openPhotoModal('${photo.url || photo}', '${photo.caption || 'Photo ' + (index + 1)}')" tabindex="0" role="button" aria-label="${photo.caption || 'Photo ' + (index + 1)}">
            <img src="${photo.thumbnail || photo.url || photo}" 
                 alt="${photo.caption || 'Inspection photo'}" 
                 loading="lazy"
                 decoding="async">
            <div class="photo-caption">${photo.caption || 'Photo ' + (index + 1)}</div>
        </div>
    `).join('');
    
    // Add keyboard support for photo items
    setupPhotoKeyboardSupport();
}

// Add keyboard support for photo items
function setupPhotoKeyboardSupport() {
    document.querySelectorAll('.photo-item').forEach(item => {
        item.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.click();
            }
        });
    });
}

// Update photos count display
function updatePhotosCount() {
    const countElement = document.getElementById('photos-count');
    const totalElement = document.getElementById('photos-total');
    
    if (countElement) countElement.textContent = filteredPhotos.length;
    if (totalElement) totalElement.textContent = allPhotos.length;
}

// Quick filter function
function quickFilter(type) {
    // Update quick filter buttons
    document.querySelectorAll('.filter-pill').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.quick === type);
    });
    
    // Reset filters with null checks
    const severityFilter = document.getElementById('severity-filter');
    const statusFilter = document.getElementById('status-filter');
    const areaFilter = document.getElementById('area-filter');
    const systemFilter = document.getElementById('system-filter');
    
    if (severityFilter) severityFilter.value = '';
    if (statusFilter) statusFilter.value = '';
    if (areaFilter) areaFilter.value = '';
    if (systemFilter) systemFilter.value = '';
    
    // Apply specific quick filter
    switch (type) {
        case 'critical':
            if (severityFilter) severityFilter.value = 'critical';
            break;
        case 'unresolved':
            if (statusFilter) statusFilter.value = 'open';
            break;
        case 'today':
            // Filter for findings from today (mock implementation)
            const today = new Date().toDateString();
            filteredFindings = allFindings.filter(f => {
                const findingDate = new Date(f.updated || f.created_at || 0);
                return findingDate.toDateString() === today;
            });
            renderFindings();
            updateFindingsCount();
            return;
    }
    
    applyFilters();
}

// Clear all filters
function clearFilters() {
    // Reset all filter inputs with null checks
    const searchInput = document.getElementById('findings-search');
    const severityFilter = document.getElementById('severity-filter');
    const statusFilter = document.getElementById('status-filter');
    const areaFilter = document.getElementById('area-filter');
    const systemFilter = document.getElementById('system-filter');
    const sortFilter = document.getElementById('sort-filter');
    
    if (searchInput) searchInput.value = '';
    if (severityFilter) severityFilter.value = '';
    if (statusFilter) statusFilter.value = '';
    if (areaFilter) areaFilter.value = '';
    if (systemFilter) systemFilter.value = '';
    if (sortFilter) sortFilter.value = 'severity-desc';
    
    // Reset quick filter pills
    document.querySelectorAll('.filter-pill').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.quick === 'all');
    });
    
    // Apply filters (will show all)
    applyFilters();
}

// Load systems information
function loadSystems() {
    const systems = reportData.systems || [];
    const container = document.getElementById('systems-list');
    
    if (systems.length === 0) {
        // Create default systems if none provided
        container.innerHTML = `
            <div class="system-card">
                <div class="system-name">Structural Components</div>
                <div class="system-details">
                    <div class="system-detail">
                        <span class="detail-label">Foundation</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                    <div class="system-detail">
                        <span class="detail-label">Walls</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                    <div class="system-detail">
                        <span class="detail-label">Roof</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                </div>
            </div>
            <div class="system-card">
                <div class="system-name">Electrical System</div>
                <div class="system-details">
                    <div class="system-detail">
                        <span class="detail-label">Service Panel</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                    <div class="system-detail">
                        <span class="detail-label">Wiring</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                </div>
            </div>
            <div class="system-card">
                <div class="system-name">Plumbing System</div>
                <div class="system-details">
                    <div class="system-detail">
                        <span class="detail-label">Water Supply</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                    <div class="system-detail">
                        <span class="detail-label">Drainage</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                </div>
            </div>
            <div class="system-card">
                <div class="system-name">HVAC System</div>
                <div class="system-details">
                    <div class="system-detail">
                        <span class="detail-label">Heating</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                    <div class="system-detail">
                        <span class="detail-label">Cooling</span>
                        <span class="detail-value">Inspected</span>
                    </div>
                </div>
            </div>
        `;
        return;
    }
    
    container.innerHTML = systems.map(system => `
        <div class="system-card">
            <div class="system-name">${system.name}</div>
            <div class="system-details">
                ${Object.entries(system.details || {}).map(([key, value]) => `
                    <div class="system-detail">
                        <span class="detail-label">${formatLabel(key)}</span>
                        <span class="detail-value">${value}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

// Switch between tabs
function switchTab(tabName, focusTab = false) {
    // Update active tab button
    document.querySelectorAll('.tab-button').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        btn.setAttribute('tabindex', isActive ? '0' : '-1');
    });
    
    // Show/hide tab panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        const isActive = pane.id === tabName;
        pane.classList.toggle('active', isActive);
        if (isActive) {
            pane.removeAttribute('hidden');
        } else {
            pane.setAttribute('hidden', '');
        }
    });
    
    // Focus the tab if requested (for keyboard navigation)
    if (focusTab) {
        const activeTab = document.querySelector(`[data-tab="${tabName}"]`);
        if (activeTab) activeTab.focus();
    }
    
    currentTab = tabName;
}

// Variables for focus management
let previousFocusElement = null;
let modalFocusableElements = [];
let modalFirstFocusable = null;
let modalLastFocusable = null;

// Open photo modal
function openPhotoModal(src, caption) {
    const modal = document.getElementById('photo-modal');
    const modalImg = document.getElementById('modal-image');
    const modalCaption = document.getElementById('modal-caption');
    
    if (!modal || !modalImg || !modalCaption) {
        console.error('Modal elements not found');
        return;
    }
    
    // Validate src URL
    if (!src || src.trim() === '') {
        console.error('Invalid photo source');
        return;
    }
    
    // Store current focus element
    previousFocusElement = document.activeElement;
    
    modal.style.display = 'block';
    modalImg.src = src;
    modalImg.alt = caption || 'Inspection photo';
    modalCaption.textContent = caption || '';
    
    // Set up focus trap
    setupModalFocusTrap();
    
    // Focus the close button
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) closeBtn.focus();
}

// Close photo modal
function closePhotoModal() {
    const modal = document.getElementById('photo-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Restore focus to previous element
    if (previousFocusElement) {
        previousFocusElement.focus();
        previousFocusElement = null;
    }
}

// Setup focus trap for modal
function setupModalFocusTrap() {
    const modal = document.getElementById('photo-modal');
    modalFocusableElements = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    if (modalFocusableElements.length > 0) {
        modalFirstFocusable = modalFocusableElements[0];
        modalLastFocusable = modalFocusableElements[modalFocusableElements.length - 1];
    }
}

// Download PDF
function downloadPDF() {
    if (!window.PDF_URL) {
        alert('PDF download URL is not available.');
        return;
    }
    window.location.href = window.PDF_URL;
}

// Set up lazy loading for images
function setupLazyLoading() {
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src || img.src;
                    img.classList.remove('lazy');
                    observer.unobserve(img);
                }
            });
        });
        
        document.querySelectorAll('img[loading="lazy"]').forEach(img => {
            imageObserver.observe(img);
        });
    }
}

// Utility function to format date
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
}

// Utility function to format relative time
function formatRelativeTime(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 7) {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else if (days > 0) {
        return `${days} day${days > 1 ? 's' : ''} ago`;
    } else if (hours > 0) {
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else if (minutes > 0) {
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else {
        return 'Just now';
    }
}

// Utility function to format labels
function formatLabel(key) {
    return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
}

// Handle keyboard shortcuts and navigation
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('photo-modal');
    const isModalOpen = modal && modal.style.display === 'block';
    
    // Modal keyboard handling
    if (isModalOpen) {
        // Close modal on Escape
        if (e.key === 'Escape') {
            closePhotoModal();
            return;
        }
        
        // Focus trap for Tab key
        if (e.key === 'Tab') {
            if (!modalFirstFocusable || !modalLastFocusable) return;
            
            if (e.shiftKey) {
                // Shift + Tab
                if (document.activeElement === modalFirstFocusable) {
                    e.preventDefault();
                    modalLastFocusable.focus();
                }
            } else {
                // Tab
                if (document.activeElement === modalLastFocusable) {
                    e.preventDefault();
                    modalFirstFocusable.focus();
                }
            }
        }
        return;
    }
    
    // Tab navigation with arrow keys
    const activeTab = document.activeElement;
    if (activeTab && activeTab.classList.contains('tab-button')) {
        const tabs = Array.from(document.querySelectorAll('.tab-button'));
        const currentIndex = tabs.indexOf(activeTab);
        
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            let newIndex;
            
            if (e.key === 'ArrowLeft') {
                newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
            } else {
                newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
            }
            
            const newTab = tabs[newIndex];
            switchTab(newTab.dataset.tab, true);
        }
        
        // Home and End keys for first/last tab
        if (e.key === 'Home') {
            e.preventDefault();
            const firstTab = tabs[0];
            switchTab(firstTab.dataset.tab, true);
        }
        
        if (e.key === 'End') {
            e.preventDefault();
            const lastTab = tabs[tabs.length - 1];
            switchTab(lastTab.dataset.tab, true);
        }
    }
    
    // Focus search on Ctrl+F or Cmd+F
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        if (currentTab === 'findings') {
            const findingsSearch = document.getElementById('findings-search');
            if (findingsSearch) findingsSearch.focus();
        } else if (currentTab === 'photos') {
            const photosSearch = document.getElementById('photos-search');
            if (photosSearch) photosSearch.focus();
        }
    }
});

// Handle modal click outside to close
document.getElementById('photo-modal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closePhotoModal();
    }
});

// Update finding status via API
async function updateFindingStatus(findingId, newStatus) {
    try {
        // Get token from URL or window
        const token = new URLSearchParams(window.location.search).get('token') || window.TOKEN;
        
        if (!token) {
            alert('Authentication required. Please ensure you have a valid token.');
            return;
        }
        
        // Capitalize first letter for API
        const statusForApi = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
        
        const response = await fetch(`/api/findings/${findingId}/status?token=${token}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: statusForApi })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update status');
        }
        
        const result = await response.json();
        
        // Update the status badge in the UI
        const statusBadge = document.getElementById(`status-${findingId}`);
        if (statusBadge) {
            statusBadge.textContent = newStatus;
            statusBadge.className = `finding-status status-${newStatus}`;
        }
        
        // Update the finding in our local data
        const finding = allFindings.find(f => f.id === findingId);
        if (finding) {
            finding.status = newStatus;
        }
        
        // Show success message (optional)
        console.log(`Finding ${findingId} status updated to ${newStatus}`);
        
    } catch (error) {
        console.error('Error updating status:', error);
        alert(`Failed to update status: ${error.message}`);
    }
}

// Show error message to user
function showErrorMessage(message) {
    const containers = [
        document.getElementById('findings-list'),
        document.getElementById('photos-grid'),
        document.getElementById('systems-list')
    ];
    
    containers.forEach(container => {
        if (container) {
            container.innerHTML = `<div class="error-message">${message}</div>`;
        }
    });
}

// Add comment to finding via API
async function addComment(findingId) {
    const commentText = prompt('Enter your comment:');
    
    if (!commentText || !commentText.trim()) {
        return;
    }
    
    try {
        // Get token from URL or window
        const token = new URLSearchParams(window.location.search).get('token') || window.TOKEN;
        
        if (!token) {
            alert('Authentication required. Please ensure you have a valid token.');
            return;
        }
        
        const response = await fetch(`/api/findings/${findingId}/comment?token=${token}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ body: commentText })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to add comment');
        }
        
        const result = await response.json();
        
        // Add comment to the UI
        const commentsContainer = document.getElementById(`comments-${findingId}`);
        if (commentsContainer) {
            const newComment = document.createElement('div');
            newComment.className = 'comment';
            newComment.innerHTML = `
                <div class="comment-author">${result.author}</div>
                <div class="comment-body">${result.body}</div>
                <div class="comment-date">Just now</div>
            `;
            commentsContainer.appendChild(newComment);
        }
        
        // Update the finding in our local data
        const finding = allFindings.find(f => f.id === findingId);
        if (finding) {
            if (!finding.comments) {
                finding.comments = [];
            }
            finding.comments.push({
                author: result.author,
                body: result.body,
                created_at: result.created_at
            });
        }
        
        // Show success message (optional)
        console.log(`Comment added to finding ${findingId}`);
        
    } catch (error) {
        console.error('Error adding comment:', error);
        alert(`Failed to add comment: ${error.message}`);
    }
}