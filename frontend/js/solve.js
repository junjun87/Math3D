/**
 * Math3D 求解模块
 * POST /api/solve → 展示解析动画 → 存储 lesson → 打开 solution.html
 */
const $textStatus = document.getElementById('text-status');

document.addEventListener('DOMContentLoaded', () => {
    const btnSubmit = document.getElementById('btn-text-submit');
    if (btnSubmit) {
        btnSubmit.addEventListener('click', async function() {
            const text = document.getElementById('text-input').value.trim();
            if (!text || this.disabled) return;
            // Loading state — prevent double submit
            this.disabled = true;
            this.textContent = '提交中…';
            try { await submitAndGo(text); }
            finally { this.disabled = false; this.textContent = '提交题目'; }
        });
    }
});

async function submitAndGo(text) {
    if (!text) return;

    // 跳转到解析动画页
    navigate('solving');
    resetSolvingUI();

    try {
        const res = await apiFetch('/api/solve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem: text })
        });
        if (!res.ok) throw new Error('求解请求失败 (' + res.status + ')');
        const data = await res.json();
        if (!data.success) throw new Error(data.error || '求解失败');

        // 保存本地历史（未登录时）
        if (!isLoggedIn()) saveLocalHistory(text, data.answer_latex, data.answer_value);

        // 标记解析完成
        markSolvingDone();

        // 短暂停留让用户看到完成状态，然后跳转
        if (data.solution_id && data.lesson) {
            sessionStorage.setItem('math3d_sol_' + data.solution_id, JSON.stringify(data.lesson));
            sessionStorage.setItem('math3d_last_problem', text);
            setTimeout(() => { window.location.href = '/solution.html?id=' + data.solution_id; }, 600);
            return;
        }

        throw new Error('服务器返回数据异常，请重试');
    } catch (e) {
        markSolvingError(e.message);
        // 3 秒后自动返回文字输入页
        setTimeout(() => navigate('text'), 3000);
    }
}

function resetSolvingUI() {
    const steps = document.querySelectorAll('#solving-steps .ss');
    steps.forEach(s => s.classList.remove('done', 'doing'));
    if (steps[0]) steps[0].classList.add('doing');
    document.getElementById('solve-title').textContent = '正在解析题目…';
}

function markSolvingDone() {
    const steps = document.querySelectorAll('#solving-steps .ss');
    steps.forEach(s => { s.classList.remove('doing'); s.classList.add('done'); });
    const spinner = document.querySelector('#solving-steps .ss .spinner');
    if (spinner) {
        spinner.outerHTML = '<svg width="14" height="14"><use href="#i-check"/></svg>';
    }
    document.getElementById('solve-title').textContent = '解析完成 ✓';
}

function markSolvingError(msg) {
    document.getElementById('solve-title').textContent = '解析失败';
    const doing = document.querySelector('#solving-steps .ss.doing');
    if (doing) {
        doing.classList.remove('doing');
        doing.querySelector('.ss-icon').innerHTML = '⚠️';
        doing.querySelector('.ss-sub').textContent = msg;
    }
}
