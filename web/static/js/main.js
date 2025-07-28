// IVR Test Management System - Main JavaScript

// Global variables
let toastContainer = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize toast container
    initializeToastContainer();
    
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize confirmation dialogs
    initializeConfirmations();
    
    // Initialize form enhancements
    initializeFormEnhancements();
    
    // Initialize auto-refresh features
    initializeAutoRefresh();
});

// Toast notification system
function initializeToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '1055';
        document.body.appendChild(toastContainer);
    }
}

function showToast(message, type = 'info', duration = 5000) {
    const toastId = 'toast-' + Date.now();
    const icons = {
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle',
        info: 'fas fa-info-circle'
    };
    
    const colors = {
        success: 'bg-success',
        error: 'bg-danger',
        warning: 'bg-warning',
        info: 'bg-primary'
    };
    
    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${colors[type]} text-white">
                <i class="${icons[type]} me-2"></i>
                <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: duration });
    
    toast.show();
    
    // Remove from DOM after hiding
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// Initialize tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize confirmation dialogs
function initializeConfirmations() {
    document.addEventListener('click', function(e) {
        if (e.target.hasAttribute('data-confirm')) {
            e.preventDefault();
            const message = e.target.getAttribute('data-confirm');
            
            if (confirm(message)) {
                if (e.target.tagName === 'A') {
                    window.location.href = e.target.href;
                } else if (e.target.tagName === 'BUTTON' && e.target.form) {
                    e.target.form.submit();
                }
            }
        }
    });
}

// Form enhancements
function initializeFormEnhancements() {
    // Auto-save draft functionality
    const forms = document.querySelectorAll('form[data-auto-save]');
    forms.forEach(function(form) {
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(function(input) {
            input.addEventListener('change', function() {
                saveDraft(form.id || 'default-form', new FormData(form));
            });
        });
        
        // Load saved draft
        loadDraft(form.id || 'default-form', form);
    });
    
    // Character counter for textareas
    const textareas = document.querySelectorAll('textarea[data-max-length]');
    textareas.forEach(function(textarea) {
        const maxLength = parseInt(textarea.getAttribute('data-max-length'));
        const counter = document.createElement('small');
        counter.className = 'form-text text-muted';
        counter.textContent = `0 / ${maxLength} characters`;
        textarea.parentNode.appendChild(counter);
        
        textarea.addEventListener('input', function() {
            const length = this.value.length;
            counter.textContent = `${length} / ${maxLength} characters`;
            
            if (length > maxLength * 0.9) {
                counter.className = 'form-text text-warning';
            } else {
                counter.className = 'form-text text-muted';
            }
        });
    });
    
    // Phone number formatting
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(function(input) {
        input.addEventListener('input', function() {
            let value = this.value.replace(/\D/g, '');
            if (value.startsWith('90')) {
                value = '+' + value;
            } else if (!value.startsWith('+')) {
                value = '+90' + value;
            }
            this.value = value;
        });
    });
}

// Auto-refresh functionality
function initializeAutoRefresh() {
    const refreshElements = document.querySelectorAll('[data-auto-refresh]');
    refreshElements.forEach(function(element) {
        const interval = parseInt(element.getAttribute('data-auto-refresh')) * 1000;
        const url = element.getAttribute('data-refresh-url') || window.location.href;
        
        setInterval(function() {
            refreshElement(element, url);
        }, interval);
    });
}

// Utility functions
function saveDraft(formId, formData) {
    try {
        const draftData = {};
        for (let [key, value] of formData.entries()) {
            draftData[key] = value;
        }
        localStorage.setItem(`draft_${formId}`, JSON.stringify(draftData));
    } catch (error) {
        console.warn('Could not save draft:', error);
    }
}

function loadDraft(formId, form) {
    try {
        const draftData = localStorage.getItem(`draft_${formId}`);
        if (draftData) {
            const data = JSON.parse(draftData);
            for (let [key, value] of Object.entries(data)) {
                const input = form.querySelector(`[name="${key}"]`);
                if (input && !input.value) {
                    input.value = value;
                }
            }
        }
    } catch (error) {
        console.warn('Could not load draft:', error);
    }
}

function clearDraft(formId) {
    try {
        localStorage.removeItem(`draft_${formId}`);
    } catch (error) {
        console.warn('Could not clear draft:', error);
    }
}

function refreshElement(element, url) {
    fetch(url)
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newElement = doc.querySelector(`#${element.id}`);
            
            if (newElement) {
                element.innerHTML = newElement.innerHTML;
            }
        })
        .catch(error => {
            console.warn('Auto-refresh failed:', error);
        });
}

// API helper functions
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, mergedOptions);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        } else {
            return await response.text();
        }
    } catch (error) {
        console.error('API request failed:', error);
        showToast(`Request failed: ${error.message}`, 'error');
        throw error;
    }
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('tr-TR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${remainingSeconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${remainingSeconds}s`;
    } else {
        return `${remainingSeconds}s`;
    }
}

// Copy to clipboard functionality
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
            showToast('Copied to clipboard', 'success', 2000);
        }).catch(function(error) {
            console.error('Copy failed:', error);
            showToast('Copy failed', 'error', 2000);
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            document.execCommand('copy');
            showToast('Copied to clipboard', 'success', 2000);
        } catch (error) {
            console.error('Copy failed:', error);
            showToast('Copy failed', 'error', 2000);
        }
        
        document.body.removeChild(textArea);
    }
}

// Export functions for global use
window.IVRTestManagement = {
    showToast,
    apiRequest,
    formatDateTime,
    formatDuration,
    copyToClipboard,
    saveDraft,
    loadDraft,
    clearDraft
};

// Service Worker registration for offline support
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(function(registration) {
                console.log('ServiceWorker registration successful');
            })
            .catch(function(error) {
                console.log('ServiceWorker registration failed');
            });
    });
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+S to save (prevent default browser save)
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        const activeForm = document.querySelector('form:focus-within, form.active');
        if (activeForm) {
            activeForm.submit();
        }
        return false;
    }
    
    // Ctrl+N to create new scenario
    if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        window.location.href = '/scenarios/create';
        return false;
    }
    
    // Escape to close modals
    if (e.key === 'Escape') {
        const openModal = document.querySelector('.modal.show');
        if (openModal) {
            const modal = bootstrap.Modal.getInstance(openModal);
            if (modal) {
                modal.hide();
            }
        }
    }
});

// Print functionality
function printPage() {
    window.print();
}

// Export data functionality
function exportToCSV(data, filename) {
    const csv = convertToCSV(data);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

function convertToCSV(objArray) {
    const array = typeof objArray !== 'object' ? JSON.parse(objArray) : objArray;
    let str = '';
    
    const headers = Object.keys(array[0]);
    str += headers.join(',') + '\r\n';
    
    for (let i = 0; i < array.length; i++) {
        let line = '';
        for (let index in headers) {
            if (line !== '') line += ',';
            line += array[i][headers[index]];
        }
        str += line + '\r\n';
    }
    
    return str;
}