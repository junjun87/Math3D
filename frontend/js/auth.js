/**
 * Math3D 认证模块
 * 管理 JWT token、用户状态、登录/注册/登出。
 */
const TOKEN_KEY = 'math3d_token';
let authToken = localStorage.getItem(TOKEN_KEY) || '';
let currentUser = null;

const $authContainer = document.getElementById('auth-container');
const $appContainer = document.getElementById('app-container');
const $appShell = document.querySelector('.app');

function isLoggedIn() { return !!authToken; }

function showAuth() {
  $authContainer.style.display = '';
  $appContainer.style.display = 'none';
  if ($appShell) $appShell.style.display = 'none';
}
function showApp() {
  $authContainer.style.display = 'none';
  $appContainer.style.display = '';
  if ($appShell) $appShell.style.display = '';
}

async function refreshUser() {
    if (!authToken) return false;
    if (isTokenExpired(authToken)) { logout(); return false; }
    try {
        const res = await apiFetch('/api/auth/me');
        if (res.ok) {
            const data = await res.json();
            if (data.success) { currentUser = data.user; return true; }
        }
    } catch {}
    logout();
    return false;
}

function logout() {
    authToken = ''; currentUser = null;
    localStorage.removeItem(TOKEN_KEY);
    showAuth();
    window.location.hash = '';
}

function updateUserUI() {
    if (!currentUser) return;
    const el = document.getElementById('home-user-phone');
    if (el) el.textContent = '\u{1F4F1} ' + currentUser.phone;
    const adminCard = document.getElementById('entry-admin-card');
    if (adminCard) adminCard.style.display = currentUser.is_admin ? '' : 'none';
}

// ── Forgot password ──
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-forgot-pwd');
    if (btn) btn.addEventListener('click', () => {
        showToast('请联系管理员重置密码', '');
    });
});

// ── Terms & Privacy links ──
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#link-terms, #link-terms-reg').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            showToast('用户协议页面暂未上线', '');
        });
    });
    document.querySelectorAll('#link-privacy, #link-privacy-reg').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            showToast('隐私政策页面暂未上线', '');
        });
    });
});
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
            document.getElementById('auth-form-' + tab.dataset.authTab).classList.add('active');
        });
    });
});

function setBtnLoading(btn, loading, originalText) {
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = loading ? '请稍候…' : originalText;
}

// ── Login ──
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('auth-form-login');
    if (!form) return;
    const btn = document.getElementById('btn-login');
    const originalText = btn ? btn.textContent : '登录';
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const phone = document.getElementById('login-phone').value.trim();
        const password = document.getElementById('login-password').value;
        const errEl = document.getElementById('login-error');
        errEl.textContent = '';
        if (!phone || !password) { errEl.textContent = '请填写手机号和密码'; return; }
        setBtnLoading(btn, true, originalText);
        try {
            const res = await apiFetch('/api/auth/login', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, password }),
            });
            const data = await res.json();
            if (!res.ok) { errEl.textContent = data.detail || '登录失败'; return; }
            authToken = data.token; currentUser = data.user;
            localStorage.setItem(TOKEN_KEY, authToken);
            updateUserUI();
            showApp();
            window.location.hash = '#home';
            try { _offerImportHistory(); } catch { /* 不影响登录主流程 */ }
        } catch { errEl.textContent = '网络错误，请重试'; }
        finally { setBtnLoading(btn, false, originalText); }
    });
});

// ── Register ──
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('auth-form-register');
    if (!form) return;
    const btn = document.getElementById('btn-register');
    const originalText = btn ? btn.textContent : '注册';
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const phone = document.getElementById('register-phone').value.trim();
        const password = document.getElementById('register-password').value;
        const password2 = document.getElementById('register-password2').value;
        const errEl = document.getElementById('register-error');
        errEl.textContent = '';
        if (!phone || !password) { errEl.textContent = '请填写手机号和密码'; return; }
        if (password !== password2) { errEl.textContent = '两次输入的密码不一致'; return; }
        if (password.length < 6) { errEl.textContent = '密码至少需要 6 位字符'; return; }
        setBtnLoading(btn, true, originalText);
        try {
            const res = await apiFetch('/api/auth/register', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, password }),
            });
            const data = await res.json();
            if (!res.ok) { errEl.textContent = data.detail || '注册失败'; return; }
            authToken = data.token; currentUser = data.user;
            localStorage.setItem(TOKEN_KEY, authToken);
            updateUserUI();
            showApp();
            window.location.hash = '#home';
            try { _offerImportHistory(); } catch { /* 不影响注册主流程 */ }
        } catch { errEl.textContent = '网络错误，请重试'; }
        finally { setBtnLoading(btn, false, originalText); }
    });
});

// ── Logout ──
document.addEventListener('DOMContentLoaded', () => {
    const btnLogout = document.getElementById('home-logout');
    if (btnLogout) btnLogout.addEventListener('click', () => {
        if (confirm('确定要退出登录吗？')) logout();
    });
    // "My" page logout button
    const meLogout = document.getElementById('me-logout-btn');
    if (meLogout) meLogout.addEventListener('click', () => {
        if (confirm('确定要退出登录吗？')) logout();
    });
});

// ── Password visibility toggle ──
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.pwd-toggle').forEach(btn => {
        // 初始态：密码隐藏中，显示"显示密码"图标
        btn.setAttribute('aria-label', '显示密码');
        const icon = btn.querySelector('use');
        if (icon) icon.setAttribute('href', '#i-eye');
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.target;
            const input = document.getElementById(targetId);
            if (!input) return;
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            if (icon) icon.setAttribute('href', isPassword ? '#i-eye-off' : '#i-eye');
            btn.setAttribute('aria-label', isPassword ? '隐藏密码' : '显示密码');
        });
    });
});

// ── Update "My" page info ──
function updateMePage() {
    if (!currentUser) return;
    const mePhone = document.getElementById('me-phone');
    const meName = document.getElementById('me-name');
    if (mePhone) mePhone.textContent = currentUser.phone;
    if (meName) meName.textContent = '📱 ' + currentUser.phone.slice(0, 3) + '****' + currentUser.phone.slice(-4);
    // Load stats
    loadMeStats();
}

async function loadMeStats() {
    try {
        const res = await apiFetch('/api/history');
        if (!res.ok) return;
        const data = await res.json();
        const items = data.items || [];
        const total = document.getElementById('me-total');
        const month = document.getElementById('me-month');
        const rate = document.getElementById('me-rate');
        if (total) total.textContent = items.length;
        if (month) {
            const now = new Date(); const y = now.getFullYear(), m = now.getMonth();
            const count = items.filter(i => {
                const d = new Date(i.created_at);
                return d.getFullYear() === y && d.getMonth() === m;
            }).length;
            month.textContent = count;
        }
        if (rate) {
            // 所有有答案的记录视为成功
            const success = items.filter(i => i.answer_latex).length;
            rate.textContent = items.length > 0 ? Math.round(success / items.length * 100) + '%' : '—';
        }
    } catch {}
}

// ── Import Toast ──
const $importToast = document.getElementById('import-toast');
const $importToastMsg = document.getElementById('import-toast-msg');

function _offerImportHistory() {
    const items = loadLocalHistory();
    if (items.length === 0) return;
    if (!$importToastMsg || !$importToast) return;
    $importToastMsg.textContent = '检测到本地有 ' + items.length + ' 条历史记录，是否导入到你的账号？';
    $importToast.classList.add('show');
}
document.addEventListener('DOMContentLoaded', () => {
    const btnYes = document.getElementById('import-toast-yes');
    const btnNo = document.getElementById('import-toast-no');
    if (!btnYes || !btnNo) return;
    btnYes.addEventListener('click', async () => {
        const items = loadLocalHistory();
        $importToast.classList.remove('show');
        if (items.length === 0) return;
        try {
            const payload = items.map(i => ({ problem: i.problem, answer_latex: i.answer_latex || '', answer_value: i.answer_value || 0 }));
            await apiFetch('/api/history/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        } catch {}
    });
    btnNo.addEventListener('click', () => $importToast.classList.remove('show'));
});
