/**
 * Math3D 历史记录模块
 * 双源：登录用户走服务端 API，未登录用户走 localStorage。
 * 支持搜索框 + 题型 chip 筛选。
 */

let _allHistoryItems = [];
let _historyFilter = '';
let _historyChip = '';

async function renderHistory() {
    const list = document.getElementById('history-list'), empty = document.getElementById('history-empty');
    if (!list) return;

    if (isLoggedIn()) {
        try {
            const res = await apiFetch('/api/history');
            if (res.ok) {
                const data = await res.json();
                _allHistoryItems = (data.items || []).map(i => ({
                    id: i.id, problem: i.problem,
                    answer_latex: i.answer_latex, answer_value: i.answer_value,
                    time: i.created_at, server: true,
                    solution_id: i.solution_id || null
                }));
            } else _allHistoryItems = loadLocalHistory();
        } catch { _allHistoryItems = loadLocalHistory(); }
    } else _allHistoryItems = loadLocalHistory();

    _applyFilters(list, empty);
}

function _applyFilters(list, empty) {
    // Apply search + chip filter
    let items = _allHistoryItems;
    if (_historyFilter) {
        const q = _historyFilter.toLowerCase();
        items = items.filter(i => i.problem.toLowerCase().includes(q));
    }
    if (_historyChip) {
        const chipMap = {
            '立方体': /正方体|长方体|立方体/,
            '四面体': /四面体/,
            '棱锥': /棱锥|四棱锥|三棱锥/,
            '棱柱': /棱柱|三棱柱|四棱柱/,
        };
        const re = chipMap[_historyChip] || new RegExp(_historyChip);
        items = items.filter(i => re.test(i.problem));
    }

    if (!items || items.length === 0) {
        empty.style.display = ''; list.querySelectorAll('.history-item').forEach(el => el.remove());
        // 更新空状态文案
        const hasAny = _allHistoryItems.length > 0;
        const eT = empty.querySelector('.e-t');
        const eS = empty.querySelector('.e-s');
        const gotoBtn = document.getElementById('h-empty-goto');
        if (eT) eT.textContent = hasAny ? '没有匹配的记录' : '暂无历史记录';
        if (eS) eS.textContent = hasAny ? '换个关键词或题型试试' : '解答题目后会自动保存在这里';
        if (gotoBtn) gotoBtn.style.display = hasAny ? 'none' : '';
        return;
    }
    empty.style.display = 'none';
    list.querySelectorAll('.history-item').forEach(el => el.remove());

    items.forEach(item => {
        const div = document.createElement('div'); div.className = 'history-item'; div.dataset.id = item.id;
        if (item.server) div.dataset.server = '1';
        const pt = item.problem.length > 80 ? item.problem.slice(0, 80) : item.problem;
        div.innerHTML =
            '<div class="history-thumb"><svg><use href="#i-scanmath"/></svg></div>' +
            '<div class="history-info"><div class="text">' + escapeHtml(pt) + '</div>' +
            '<div class="answer">答案：' + escapeHtml(item.answer_latex || '') + '</div>' +
            '<div class="time">' + formatTime(item.time) + '</div></div>' +
            '<button class="history-delete" data-id="' + item.id + '"><svg width="14" height="14"><use href="#i-delete"/></svg></button>';
        div.addEventListener('click', e => {
            if (!e.target.closest('.history-delete')) {
                if (item.server && item.solution_id) {
                    window.location.href = '/solution.html?id=' + item.solution_id;
                } else {
                    document.getElementById('text-input').value = pt; navigate('text');
                }
            }
        });
        list.appendChild(div);
    });
}

async function deleteHistoryItem(id) {
    if (!confirm('确定要删除这条记录吗？')) return;
    if (isLoggedIn()) { try { await apiFetch('/api/history/' + id, { method: 'DELETE' }); } catch {} }
    else { localStorage.setItem(HISTORY_KEY, JSON.stringify(loadLocalHistory().filter(i => i.id !== id))); }
    renderHistory();
}

async function clearHistory() {
    if (!confirm(isLoggedIn() ? '确定要清除所有历史记录吗？（跨设备同步删除）' : '确定要清除所有历史记录吗？')) return;
    if (isLoggedIn()) { try { await apiFetch('/api/history', { method: 'DELETE' }); } catch {} }
    else localStorage.removeItem(HISTORY_KEY);
    _allHistoryItems = [];
    renderHistory();
}

// ── Bind events ──
document.addEventListener('DOMContentLoaded', () => {
    const historyList = document.getElementById('history-list');
    if (historyList) historyList.addEventListener('click', e => {
        const btn = e.target.closest('.history-delete');
        if (btn) { e.stopPropagation(); deleteHistoryItem(btn.dataset.id); }
    });
    const btnClear = document.getElementById('btn-clear-history');
    if (btnClear) btnClear.addEventListener('click', clearHistory);

    // Search
    const searchInput = document.getElementById('history-search');
    if (searchInput) searchInput.addEventListener('input', () => {
        _historyFilter = searchInput.value.trim();
        const list = document.getElementById('history-list'), empty = document.getElementById('history-empty');
        if (list) _applyFilters(list, empty);
    });

    // Filter chips
    const chipsContainer = document.getElementById('history-chips');
    if (chipsContainer) chipsContainer.addEventListener('click', e => {
        const chip = e.target.closest('.chip');
        if (!chip) return;
        chipsContainer.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        _historyChip = chip.dataset.filter || '';
        const list = document.getElementById('history-list'), empty = document.getElementById('history-empty');
        if (list) _applyFilters(list, empty);
    });
});
