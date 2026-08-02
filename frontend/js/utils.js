/**
 * Math3D 工具函数
 */

// 应用版本号——单一来源，页面通过 APP_VERSION 读取
const APP_VERSION = '0.6.0';

function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function formatTime(ts) {
    const d = (typeof ts === 'number') ? new Date(ts) : new Date(ts);
    if (isNaN(d.getTime())) return ts || '';
    return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' +
        String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
}

function _jwtPayload(token) {
    try { const p = token.split('.')[1]; return JSON.parse(atob(p)); }
    catch { return null; }
}

function isTokenExpired(token) {
    const p = _jwtPayload(token);
    return (!p || !p.exp || Date.now() / 1000 > p.exp);
}

// ── 全局异常兜底 ──
window.addEventListener('error', function(e) {
    console.error('Math3D global error:', e.message, e.filename, e.lineno);
    // 重置所有 loading 态文字
    document.querySelectorAll('.status-msg.loading').forEach(function(el) {
        el.textContent = '出错了，请重试';
        el.className = 'status-msg error show';
    });
});
window.addEventListener('unhandledrejection', function(e) {
    console.error('Math3D unhandled rejection:', e.reason);
    document.querySelectorAll('.status-msg.loading').forEach(function(el) {
        el.textContent = '网络异常，请检查连接后重试';
        el.className = 'status-msg error show';
    });
});

// LocalStorage history utilities (used when not logged in)
const HISTORY_KEY = 'math3d_history';
function loadLocalHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; } }
function saveLocalHistory(problem, al, av) {
    const items = loadLocalHistory();
    items.unshift({ id: Date.now().toString(36) + Math.random().toString(36).slice(2,6), problem: problem.slice(0, 80), answer_latex: al, answer_value: av, time: Date.now() });
    if (items.length > 50) items.length = 50;
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
}

// ── Global toast (CSS-driven, theme-aware) ──
function showToast(msg, type) {
    document.querySelectorAll('.global-toast').forEach(t => t.remove());
    const toast = document.createElement('div');
    toast.className = 'global-toast ' + (type || 'success');
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(function() {
        toast.classList.add('out');
        setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
    }, 2000);
}
