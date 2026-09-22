(() => {
  const usersBody = document.getElementById('users-body');
  const nodesBody = document.getElementById('nodes-body');
  const detailEl = document.getElementById('detail');

  const userDialog = document.getElementById('user-dialog');
  const userForm = document.getElementById('user-form');
  const nodeDialog = document.getElementById('node-dialog');
  const nodeForm = document.getElementById('node-form');
  const passwordDialog = document.getElementById('password-dialog');
  const passwordForm = document.getElementById('password-form');

  let allNodes = [];

  async function loadNodes() {
    const data = await api('GET', '/nodes?size=100');
    allNodes = data.items;
  }

  function nodeOptionsHtml(selectedId) {
    return ['<option value="">— не выбрано —</option>']
      .concat(allNodes.map((n) => `<option value="${n.id}" ${n.id === selectedId ? 'selected' : ''}>${escapeHtml(n.name)} (${n.type === 'SERVICE_POINT' ? 'ПО' : 'СЦ'})</option>`))
      .join('');
  }

  async function loadUsers() {
    const data = await api('GET', '/admin/users?size=100');
    usersBody.innerHTML = '';
    for (const u of data.items) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${escapeHtml(u.login)}</td><td>${escapeHtml(u.role)}</td>
        <td>${escapeHtml(u.node ? u.node.name : '—')}</td>
        <td>${u.blocked ? 'Заблокирован' : 'Активен'}</td>`;
      tr.addEventListener('click', () => selectUser(u.id));
      usersBody.appendChild(tr);
    }
  }

  async function loadNodesTab() {
    const data = await api('GET', '/nodes?size=100');
    nodesBody.innerHTML = '';
    for (const n of data.items) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${escapeHtml(n.name)}</td>
        <td>${n.type === 'SERVICE_POINT' ? 'Пункт обслуживания' : 'Сортировочный центр'}</td>
        <td>${escapeHtml(n.address)}</td>
        <td>${n.active ? 'Да' : 'Нет'}</td>`;
      tr.addEventListener('click', () => selectNode(n.id));
      nodesBody.appendChild(tr);
    }
  }

  function renderUser(u) {
    detailEl.innerHTML = `
      <h2>Сотрудник</h2>
      <dl class="kv">
        <dt>Логин</dt><dd>${escapeHtml(u.login)}</dd>
        <dt>ФИО</dt><dd>${escapeHtml(u.fullName)}</dd>
        <dt>Роль</dt><dd>${escapeHtml(u.role)}</dd>
        <dt>Узел</dt><dd>${escapeHtml(u.node ? u.node.name : '—')}</dd>
        <dt>Состояние</dt><dd>${u.blocked ? 'Заблокирован' : 'Активен'}</dd>
      </dl>
      <div class="row">
        <button id="edit-user">Редактировать</button>
        <button id="set-password">Задать новый пароль</button>
        <span class="spacer"></span>
        ${u.blocked
          ? '<button class="primary" id="unblock-user">Разблокировать</button>'
          : '<button class="danger" id="block-user">Заблокировать</button>'}
      </div>
    `;
    document.getElementById('edit-user').addEventListener('click', () => openUserDialog(u));
    document.getElementById('set-password').addEventListener('click', () => openPasswordDialog(u));
    if (document.getElementById('block-user')) {
      document.getElementById('block-user').addEventListener('click', async () => {
        if (!confirm('Заблокировать сотрудника?')) return;
        try { await api('POST', `/admin/users/${u.id}/block`); toast('Сотрудник заблокирован'); loadUsers(); selectUser(u.id); }
        catch (e) { toast(e.message, 'error'); }
      });
    }
    if (document.getElementById('unblock-user')) {
      document.getElementById('unblock-user').addEventListener('click', async () => {
        try { await api('POST', `/admin/users/${u.id}/unblock`); toast('Сотрудник разблокирован'); loadUsers(); selectUser(u.id); }
        catch (e) { toast(e.message, 'error'); }
      });
    }
  }

  function renderNode(n) {
    detailEl.innerHTML = `
      <h2>Узел доставки</h2>
      <dl class="kv">
        <dt>Название</dt><dd>${escapeHtml(n.name)}</dd>
        <dt>Тип</dt><dd>${n.type === 'SERVICE_POINT' ? 'Пункт обслуживания' : 'Сортировочный центр'}</dd>
        <dt>Адрес</dt><dd>${escapeHtml(n.address)}</dd>
        <dt>Активен</dt><dd>${n.active ? 'Да' : 'Нет'}</dd>
      </dl>
      <div class="row">
        <button id="edit-node">Редактировать</button>
        <span class="spacer"></span>
        ${n.active ? '<button class="danger" id="deactivate-node">Деактивировать</button>' : ''}
      </div>
    `;
    document.getElementById('edit-node').addEventListener('click', () => openNodeDialog(n));
    if (document.getElementById('deactivate-node')) {
      document.getElementById('deactivate-node').addEventListener('click', async () => {
        if (!confirm('Деактивировать узел?')) return;
        try { await api('POST', `/admin/nodes/${n.id}/deactivate`); toast('Узел деактивирован'); loadNodes(); loadNodesTab(); selectNode(n.id); }
        catch (e) { toast(e.message, 'error'); }
      });
    }
  }

  async function selectUser(id) {
    const u = await api('GET', `/admin/users/${id}`);
    renderUser(u);
  }
  async function selectNode(id) {
    const n = await api('GET', `/nodes/${id}`);
    renderNode(n);
  }

  async function openUserDialog(u) {
    await loadNodes();
    userForm.reset();
    userForm.querySelector('[name="id"]').value = u ? u.id : '';
    document.getElementById('user-dialog-title').textContent = u ? 'Редактирование сотрудника' : 'Новый сотрудник';
    const pwdField = document.getElementById('password-field');
    if (u) {
      userForm.querySelector('[name="login"]').value = u.login;
      userForm.querySelector('[name="fullName"]').value = u.fullName;
      userForm.querySelector('[name="role"]').value = u.role;
      userForm.querySelector('[name="nodeId"]').innerHTML = nodeOptionsHtml(u.node ? u.node.id : null);
      pwdField.hidden = true;
      userForm.querySelector('[name="password"]').required = false;
    } else {
      userForm.querySelector('[name="nodeId"]').innerHTML = nodeOptionsHtml(null);
      pwdField.hidden = false;
      userForm.querySelector('[name="password"]').required = true;
    }
    userDialog.showModal();
  }

  document.getElementById('new-user-btn').addEventListener('click', () => openUserDialog(null));
  document.getElementById('user-cancel').addEventListener('click', () => userDialog.close());

  userForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(userForm);
    const id = fd.get('id');
    const role = fd.get('role');
    const nodeIdRaw = fd.get('nodeId');
    const payload = {
      login: fd.get('login'),
      fullName: fd.get('fullName'),
      role,
      nodeId: nodeIdRaw ? Number(nodeIdRaw) : null,
    };
    try {
      if (id) {
        await api('PATCH', `/admin/users/${id}`, payload);
        toast('Сотрудник обновлён');
      } else {
        payload.password = fd.get('password');
        await api('POST', '/admin/users', payload);
        toast('Сотрудник создан');
      }
      userDialog.close();
      loadUsers();
      loadNodes();
    } catch (err) {
      const details = (err.fieldErrors || []).map((f) => `${f.field}: ${f.message}`).join('\n');
      toast((err.message || 'Ошибка') + (details ? ' — ' + details : ''), 'error');
    }
  });

  function openNodeDialog(n) {
    nodeForm.reset();
    nodeForm.querySelector('[name="id"]').value = n ? n.id : '';
    document.getElementById('node-dialog-title').textContent = n ? 'Редактирование узла' : 'Новый узел';
    if (n) {
      nodeForm.querySelector('[name="name"]').value = n.name;
      nodeForm.querySelector('[name="type"]').value = n.type;
      nodeForm.querySelector('[name="address"]').value = n.address;
    }
    nodeDialog.showModal();
  }

  document.getElementById('new-node-btn').addEventListener('click', () => openNodeDialog(null));
  document.getElementById('node-cancel').addEventListener('click', () => nodeDialog.close());

  nodeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(nodeForm);
    const id = fd.get('id');
    const payload = { name: fd.get('name'), type: fd.get('type'), address: fd.get('address') };
    try {
      if (id) {
        await api('PATCH', `/admin/nodes/${id}`, payload);
        toast('Узел обновлён');
      } else {
        await api('POST', '/admin/nodes', payload);
        toast('Узел создан');
      }
      nodeDialog.close();
      loadNodes();
      loadNodesTab();
    } catch (err) {
      const details = (err.fieldErrors || []).map((f) => `${f.field}: ${f.message}`).join('\n');
      toast((err.message || 'Ошибка') + (details ? ' — ' + details : ''), 'error');
    }
  });

  function openPasswordDialog(u) {
    passwordForm.reset();
    passwordForm.querySelector('[name="id"]').value = u.id;
    passwordDialog.showModal();
  }
  document.getElementById('password-cancel').addEventListener('click', () => passwordDialog.close());
  passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(passwordForm);
    try {
      await api('PUT', `/admin/users/${fd.get('id')}/password`, { newPassword: fd.get('newPassword') });
      toast('Пароль изменён');
      passwordDialog.close();
    } catch (err) {
      const details = (err.fieldErrors || []).map((f) => `${f.field}: ${f.message}`).join('\n');
      toast((err.message || 'Ошибка') + (details ? ' — ' + details : ''), 'error');
    }
  });

  document.querySelectorAll('.tab').forEach((el) => {
    el.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
      el.classList.add('active');
      const tab = el.dataset.tab;
      document.getElementById('tab-users').hidden = tab !== 'users';
      document.getElementById('tab-nodes').hidden = tab !== 'nodes';
      detailEl.innerHTML = '<p class="hint">Выберите запись.</p>';
    });
  });

  loadNodes().then(() => { loadUsers(); loadNodesTab(); });
})();