async function api(method, path, body) {
  const res = await fetch('/api/v1' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    credentials: 'same-origin',
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (_) { data = {}; }
  if (!res.ok) {
    if (res.status === 401 && location.pathname !== '/login' && location.pathname !== '/tracking') {
      location.href = '/login';
    }
    const err = new Error((data && data.message) || 'Ошибка запроса');
    err.status = res.status;
    err.code = data && data.code;
    err.fieldErrors = (data && data.fieldErrors) || [];
    throw err;
  }
  return data;
}

function toast(message, kind = 'ok') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.className = 'toast ' + kind;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 3500);
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

document.addEventListener('click', (e) => {
  if (e.target.id === 'logout-btn') {
    api('POST', '/auth/logout').finally(() => location.href = '/login');
  }
});