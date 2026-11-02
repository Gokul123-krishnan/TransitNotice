// TransitNotice – Salem City Bus Transit Update Tracker JavaScript

document.addEventListener('DOMContentLoaded', () => {
    initLiveClock();
    initSidebarToggle();
    initNotificationTray();
    initClientFilter();
    initNoticeCopyLink();
});

// 1. Live IST Clock
function initLiveClock() {
    const clockElem = document.getElementById('live-ist-clock-text');
    if (!clockElem) return;

    function updateClock() {
        const now = new Date();
        // Format to Asia/Kolkata
        const options = {
            timeZone: 'Asia/Kolkata',
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        };
        const formatter = new Intl.DateTimeFormat('en-GB', options);
        clockElem.textContent = formatter.format(now) + ' IST';
    }

    updateClock();
    setInterval(updateClock, 1000);
}

// 2. Responsive Sidebar Toggle for Mobile
function initSidebarToggle() {
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    const sidebar = document.getElementById('app-sidebar');
    if (!toggleBtn || !sidebar) return;

    toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sidebar.classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
        if (sidebar.classList.contains('show') && !sidebar.contains(e.target) && e.target !== toggleBtn) {
            sidebar.classList.remove('show');
        }
    });
}

// 3. Notification Tray & Real-time Read Handler
function initNotificationTray() {
    const bellBtn = document.getElementById('notification-bell-btn');
    const scrollContainer = document.getElementById('notifications-scroll-list');
    const badgeCounter = document.getElementById('notification-badge');
    const markAllBtn = document.getElementById('mark-all-read-btn');

    if (!bellBtn || !scrollContainer) return;

    // Load recent notifications when dropdown opened
    bellBtn.addEventListener('click', () => {
        fetch('/api/notifications')
            .then(res => res.json())
            .then(data => {
                renderNotifications(data.notifications, data.unread_count);
            })
            .catch(err => console.error('Failed to load notifications:', err));
    });

    function renderNotifications(items, unreadCount) {
        if (badgeCounter) {
            badgeCounter.textContent = unreadCount;
            badgeCounter.style.display = unreadCount > 0 ? 'flex' : 'none';
        }

        if (!items || items.length === 0) {
            scrollContainer.innerHTML = `
                <div class="p-4 text-center text-muted">
                    <i class="fas fa-bell-slash fa-2x mb-2 text-secondary"></i>
                    <p class="small mb-0">No recent transit notices.</p>
                </div>
            `;
            return;
        }

        let html = '';
        items.forEach(item => {
            const unreadClass = item.is_read ? '' : 'unread';
            const iconMap = {
                'NEW_NOTICE': 'fa-bullhorn text-primary',
                'MODIFIED_ROUTE': 'fa-route text-warning',
                'EXTENDED_INTERRUPTION': 'fa-clock text-warning',
                'CANCELLED_NOTICE': 'fa-ban text-danger',
                'RESTORED_SERVICE': 'fa-check-circle text-success'
            };
            const iconClass = iconMap[item.notification_type] || 'fa-info-circle text-info';

            html += `
                <div class="notification-item ${unreadClass}" data-id="${item.notification_id}">
                    <div class="d-flex align-items-start gap-2">
                        <i class="fas ${iconClass} mt-1"></i>
                        <div class="flex-grow-1">
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <strong class="small text-dark">${escapeHtml(item.title)}</strong>
                                <span class="text-muted" style="font-size: 0.68rem;">${formatTimeAgo(item.created_at)}</span>
                            </div>
                            <p class="mb-1 text-muted" style="font-size: 0.78rem;">${escapeHtml(item.message)}</p>
                            ${!item.is_read ? `
                                <button class="btn btn-link btn-sm p-0 mark-single-read" style="font-size: 0.7rem; color: #0891b2;" onclick="markSingleRead(${item.notification_id}, event)">
                                    <i class="fas fa-check"></i> Mark read
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        scrollContainer.innerHTML = html;
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', (e) => {
            e.preventDefault();
            fetch('/api/notifications/read-all', { method: 'POST' })
                .then(res => res.json())
                .then(() => {
                    if (badgeCounter) {
                        badgeCounter.textContent = '0';
                        badgeCounter.style.display = 'none';
                    }
                    document.querySelectorAll('.notification-item.unread').forEach(el => {
                        el.classList.remove('unread');
                        const btn = el.querySelector('.mark-single-read');
                        if (btn) btn.remove();
                    });
                })
                .catch(err => console.error('Failed to mark all read:', err));
        });
    }
}

window.markSingleRead = function(nid, evt) {
    if (evt) evt.stopPropagation();
    fetch(`/api/notifications/read/${nid}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            const item = document.querySelector(`.notification-item[data-id="${nid}"]`);
            if (item) {
                item.classList.remove('unread');
                const btn = item.querySelector('.mark-single-read');
                if (btn) btn.remove();
            }
            const badgeCounter = document.getElementById('notification-badge');
            if (badgeCounter) {
                badgeCounter.textContent = data.unread_count;
                if (data.unread_count <= 0) badgeCounter.style.display = 'none';
            }
        })
        .catch(err => console.error(err));
};

// 4. Quick Client-Side Filter for Tables and Cards
function initClientFilter() {
    const quickInput = document.getElementById('quick-client-filter');
    if (!quickInput) return;

    quickInput.addEventListener('input', (e) => {
        const val = e.target.value.toLowerCase().trim();
        const targets = document.querySelectorAll('.filterable-item');

        targets.forEach(el => {
            const text = el.textContent.toLowerCase();
            el.style.display = text.includes(val) ? '' : 'none';
        });
    });
}

// 5. Copy Notice Link Helper
function initNoticeCopyLink() {
    document.querySelectorAll('.copy-notice-link-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const noticeId = btn.getAttribute('data-notice-id');
            const url = `${window.location.origin}/notices/${noticeId}`;
            navigator.clipboard.writeText(url).then(() => {
                const orig = btn.innerHTML;
                btn.innerHTML = `<i class="fas fa-check text-success"></i> Copied!`;
                setTimeout(() => {
                    btn.innerHTML = orig;
                }, 2000);
            });
        });
    });
}

// Helper: Escape HTML string
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, function(m) {
        return ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        })[m];
    });
}

// Helper: Relative time ago
function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr.replace(' ', 'T') + '+05:30');
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
}
