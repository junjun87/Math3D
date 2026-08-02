/**
 * Math3D 管理员模块
 * 用户列表、查看历史、删除用户、提升管理员。
 */

async function renderAdminUsers() {
    const list = document.getElementById('admin-user-list');
    const empty = document.getElementById('admin-empty');
    try {
        const res = await apiFetch('/api/admin/users');
        const data = await res.json();
        if (!data.success) { empty.innerHTML = '<div class="e-icon"><svg><use href="#i-delete"/></svg></div><p>加载失败</p>'; return; }
        if (data.users.length === 0) { empty.innerHTML = '<div class="e-icon"><svg><use href="#i-user"/></svg></div><p>暂无用户</p>'; return; }
        empty.style.display = 'none';
        list.querySelectorAll('.history-item,.admin-user-item').forEach(el => el.remove());

        data.users.forEach(u => {
            const div = document.createElement('div');
            div.className = 'history-item admin-user-item';
            const isAdmin = u.is_admin;
            div.innerHTML =
                '<div class="history-thumb" style="background:' + (isAdmin ? '#fef3c7' : 'var(--g50)') + ';color:' + (isAdmin ? '#f59e0b' : 'var(--label-3)') + '">' +
                    '<svg width="20" height="20"><use href="' + (isAdmin ? '#i-settings' : '#i-user') + '"/></svg>' +
                '</div>' +
                '<div class="history-info">' +
                    '<div class="text">' + escapeHtml(u.phone) + (isAdmin ? ' <span style="font-size:11px;color:var(--orange);font-weight:500">管理员</span>' : '') + '</div>' +
                    '<div class="time">' + u.created_at + ' · 解题 ' + u.history_count + ' 次</div>' +
                '</div>' +
                '<button class="history-delete admin-view-btn" data-uid="' + u.id + '" data-phone="' + u.phone + '" title="查看历史">' +
                    '<svg width="16" height="16"><use href="#i-search"/></svg></button>' +
                (isAdmin ? '' : '<button class="history-delete admin-del-btn" data-uid="' + u.id + '" data-phone="' + u.phone + '" title="删除用户">' +
                    '<svg width="16" height="16"><use href="#i-delete"/></svg></button>');
            list.appendChild(div);
        });

        // View user history
        list.querySelectorAll('.admin-view-btn').forEach(btn => {
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                const uid = btn.dataset.uid;
                const phone = btn.dataset.phone;
                document.getElementById('admin-history-title').textContent = phone + ' 的解题记录';
                navigate('admin-history');
                const hlist = document.getElementById('admin-history-list');
                hlist.innerHTML = '<div class="empty-state"><div class="e-icon"><div class="spinner"></div></div><p>加载中...</p></div>';
                try {
                    const r = await apiFetch('/api/admin/users/' + uid + '/history');
                    const d = await r.json();
                    if (!d.success) { hlist.innerHTML = '<div class="empty-state"><div class="e-icon"><svg><use href="#i-delete"/></svg></div><p>加载失败</p></div>'; return; }
                    if (d.items.length === 0) { hlist.innerHTML = '<div class="empty-state"><div class="e-icon"><svg><use href="#i-history"/></svg></div><p>暂无记录</p></div>'; return; }
                    hlist.innerHTML = '';
                    d.items.forEach(item => {
                        const dv = document.createElement('div'); dv.className = 'history-item';
                        const pt = item.problem.length > 80 ? item.problem.slice(0, 80) : item.problem;
                        dv.innerHTML = '<div class="history-thumb"><svg width="20" height="20"><use href="#i-scanmath"/></svg></div><div class="history-info"><div class="text">' + escapeHtml(pt) + '</div><div class="answer">答案：' + escapeHtml(item.answer_latex || '') + '</div><div class="time">' + item.created_at + '</div></div>';
                        if (item.solution_id) {
                            dv.style.cursor = 'pointer';
                            dv.addEventListener('click', () => { window.location.href = '/solution.html?id=' + item.solution_id; });
                        }
                        hlist.appendChild(dv);
                    });
                } catch { hlist.innerHTML = '<div class="empty-state"><div class="e-icon"><svg><use href="#i-delete"/></svg></div><p>网络错误</p></div>'; }
            });
        });

        // Delete user
        list.querySelectorAll('.admin-del-btn').forEach(btn => {
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                if (!confirm('确定要删除用户 ' + btn.dataset.phone + ' 及其所有记录吗？此操作不可撤销。')) return;
                try { await apiFetch('/api/admin/users/' + btn.dataset.uid, { method: 'DELETE' }); } catch {}
                renderAdminUsers();
            });
        });
    } catch { empty.innerHTML = '<div class="e-icon"><svg><use href="#i-delete"/></svg></div><p>网络错误</p></div>'; }
}

// ── Promote ──
document.addEventListener('DOMContentLoaded', () => {
    const btnPromote = document.getElementById('btn-promote');
    if (!btnPromote) return;
    btnPromote.addEventListener('click', async () => {
        const phone = document.getElementById('promote-phone').value.trim();
        if (!phone) return;
        if (!confirm('确定将 ' + phone + ' 提升为管理员吗？')) return;
        try {
            const res = await apiFetch('/api/admin/promote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: phone })
            });
            const data = await res.json();
            if (res.ok) { document.getElementById('promote-phone').value = ''; renderAdminUsers(); }
            showToast(data.detail || data.message || (res.ok ? '提升成功' : '操作失败'), res.ok ? 'success' : 'error');
        } catch { showToast('网络错误', 'error'); }
    });
});
