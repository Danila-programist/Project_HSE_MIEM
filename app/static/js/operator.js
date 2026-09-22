(() => {
  let page = 1, size = 20, totalPages = 1, currentTrack = '';
  let selectedId = null;

  const listBody = document.getElementById('shipments-body');
  const detailEl = document.getElementById('detail');

  async function loadList() {
    const params = new URLSearchParams({ page, size, direction: 'ALL' });
    if (currentTrack) params.set('trackNumber', currentTrack);
    const data = await api('GET', '/shipments?' + params.toString());
    totalPages = Math.max(1, data.totalPages);
    listBody.innerHTML = '';
    for (const s of data.items) {
      const tr = document.createElement('tr');
      if (s.id === selectedId) tr.classList.add('selected');
      tr.innerHTML = `<td>${escapeHtml(s.trackNumber)}</td><td>${escapeHtml(s.statusName)}</td>
        <td><button class="link">Открыть</button></td>`;
      tr.addEventListener('click', () => openCard(s.id));
      listBody.appendChild(tr);
    }
    document.getElementById('page-info').textContent = `Страница ${data.page} из ${totalPages}`;
  }

  async function openCard(id) {
    selectedId = id;
    const s = await api('GET', `/shipments/${id}`);
    renderCard(s);
    loadList().catch(() => {});
  }

  function renderCard(s) {
    const actions = [];
    if (s.status === 'CREATED') {
      actions.push(`<div class="card"><h2>Приём отправления</h2>
        <div class="grid2">
          <label>Тип документа<select id="sender-doc-type"></select></label>
          <label>Серия<input id="sender-doc-series" maxlength="20"></label>
          <label>Номер<input id="sender-doc-number" maxlength="30" required></label>
        </div>
        <div class="row">
          <span class="spacer"></span>
          <button class="primary" id="accept-btn">Подтвердить приём</button>
        </div>
      </div>`);
    } else if (s.status === 'ACCEPTED') {
      actions.push(`<div class="card"><h2>Отправка в следующий узел</h2>
        <label>Следующий узел<select id="next-node"></select></label>
        <div class="row"><span class="spacer"></span>
          <button class="primary" id="dispatch-btn">Отправить в следующий узел</button>
        </div>
      </div>`);
    } else if (s.status === 'READY_FOR_PICKUP') {
      actions.push(`<div class="card"><h2>Выдача отправления</h2>
        <div class="grid2">
          <label>Тип документа<select id="recipient-doc-type"></select></label>
          <label>Серия<input id="recipient-doc-series" maxlength="20"></label>
          <label>Номер<input id="recipient-doc-number" maxlength="30" required></label>
        </div>
        <div class="row"><span class="spacer"></span>
          <button class="primary" id="issue-btn">Выдать отправление</button>
        </div>
      </div>`);
    }

    detailEl.innerHTML = `
      <div class="row">
        <h2 style="margin:0">${escapeHtml(s.trackNumber)}</h2>
        <span class="spacer"></span>
      </div>
      <div class="status-banner"><div class="status-name">${escapeHtml(s.statusName)}</div></div>
      <dl class="kv">
        <dt>Тип</dt><dd>${escapeHtml(s.shipmentType.name)}</dd>
        <dt>Габариты</dt><dd>${s.weightKg} кг · ${s.lengthCm} × ${s.widthCm} × ${s.heightCm} см</dd>
        <dt>Описание</dt><dd>${escapeHtml(s.description || '—')}</dd>
        <dt>Пункт приёма</dt><dd>${escapeHtml(s.originNode.name)}</dd>
        <dt>Пункт назначения</dt><dd>${escapeHtml(s.destinationNode.name)}</dd>
        <dt>Текущий узел</dt><dd>${escapeHtml(s.currentNode.name)}</dd>
        <dt>Следующий узел</dt><dd>${escapeHtml(s.nextNode ? s.nextNode.name : '—')}</dd>
        <dt>Адрес доставки</dt><dd>${escapeHtml(s.deliveryAddress)}</dd>
        <dt>Отправитель</dt><dd>${escapeHtml(s.sender ? s.sender.fullName + ' ' + s.sender.phone : '—')}</dd>
        <dt>Получатель</dt><dd>${escapeHtml(s.recipient ? s.recipient.fullName + ' ' + s.recipient.phone : '—')}</dd>
        <dt>Создано</dt><dd>${fmtDate(s.createdAt)}</dd>
        <dt>Принято</dt><dd>${fmtDate(s.acceptedAt)}</dd>
        <dt>Выдано</dt><dd>${fmtDate(s.issuedAt)}</dd>
      </dl>
      ${actions.join('')}
    `;

    if (document.getElementById('accept-btn')) {
      wireAccept(s.id);
      fillDocumentTypes('sender-doc-type');
    }
    if (document.getElementById('dispatch-btn')) {
      wireDispatch(s.id, s);
    }
    if (document.getElementById('issue-btn')) {
      wireIssue(s.id);
      fillDocumentTypes('recipient-doc-type');
    }
  }

  async function fillDocumentTypes(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    try {
      const items = await api('GET', '/dictionaries/document-types');
      sel.innerHTML = items.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join('');
    } catch (_) {}
  }

  function wireAccept(id) {
    document.getElementById('accept-btn').addEventListener('click', async () => {
      try {
        const payload = {
          senderDocument: {
            documentTypeId: Number(document.getElementById('sender-doc-type').value),
            series: document.getElementById('sender-doc-series').value || null,
            number: document.getElementById('sender-doc-number').value,
          },
        };
        const s = await api('POST', `/shipments/${id}/accept`, payload);
        renderCard(s);
        loadList().catch(() => {});
        toast('Отправление принято');
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  async function wireDispatch(id, s) {
    const sel = document.getElementById('next-node');
    const nodes = await api('GET', '/nodes?active=true&size=100');
    const destId = s.destinationNode.id;
    const filtered = nodes.items.filter((n) => n.type === 'SORTING_CENTER' || n.id === destId);
    sel.innerHTML = filtered.map((n) => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
    document.getElementById('dispatch-btn').addEventListener('click', async () => {
      try {
        const updated = await api('POST', `/shipments/${id}/dispatch`, { nextNodeId: Number(sel.value) });
        renderCard(updated);
        loadList().catch(() => {});
        toast('Отправление отправлено');
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  function wireIssue(id) {
    document.getElementById('issue-btn').addEventListener('click', async () => {
      try {
        const payload = {
          recipientDocument: {
            documentTypeId: Number(document.getElementById('recipient-doc-type').value),
            series: document.getElementById('recipient-doc-series').value || null,
            number: document.getElementById('recipient-doc-number').value,
          },
        };
        const s = await api('POST', `/shipments/${id}/issue`, payload);
        renderCard(s);
        loadList().catch(() => {});
        toast('Отправление выдано');
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  const dialog = document.getElementById('create-dialog');
  const form = document.getElementById('create-form');

  async function openCreateDialog() {
    const [nodes, types] = await Promise.all([
      api('GET', '/nodes?active=true&type=SERVICE_POINT&size=100'),
      api('GET', '/dictionaries/shipment-types'),
    ]);
    const me = JSON.parse(document.getElementById('page-data').textContent).user;
    const myNodeId = me.node ? me.node.id : null;
    const nodeSel = form.querySelector('[name="destinationNodeId"]');
    const typeSel = form.querySelector('[name="shipmentTypeId"]');
    form.reset();
    nodeSel.innerHTML = nodes.items
      .filter((n) => n.id !== myNodeId)
      .map((n) => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
    typeSel.innerHTML = types.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
    dialog.showModal();
  }

  document.getElementById('new-shipment-btn').addEventListener('click', openCreateDialog);
  document.getElementById('create-cancel').addEventListener('click', () => dialog.close());

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {
      sender: { fullName: fd.get('sender.fullName'), phone: fd.get('sender.phone') },
      recipient: { fullName: fd.get('recipient.fullName'), phone: fd.get('recipient.phone') },
      destinationNodeId: Number(fd.get('destinationNodeId')),
      shipmentTypeId: Number(fd.get('shipmentTypeId')),
      weightKg: Number(fd.get('weightKg')),
      lengthCm: Number(fd.get('lengthCm')),
      widthCm: Number(fd.get('widthCm')),
      heightCm: Number(fd.get('heightCm')),
      description: fd.get('description') || null,
    };
    try {
      const s = await api('POST', '/shipments', payload);
      dialog.close();
      toast('Отправление оформлено: ' + s.trackNumber);
      selectedId = s.id;
      renderCard(s);
      page = 1;
      loadList().catch(() => {});
    } catch (err) {
      const details = (err.fieldErrors || []).map((f) => `${f.field}: ${f.message}`).join('\n');
      toast((err.message || 'Ошибка') + (details ? ' — ' + details : ''), 'error');
    }
  });

  document.getElementById('search-form').addEventListener('submit', (e) => {
    e.preventDefault();
    currentTrack = e.target.trackNumber.value.trim();
    page = 1;
    loadList().catch(() => {});
  });
  document.getElementById('reset-btn').addEventListener('click', () => {
    currentTrack = '';
    document.querySelector('#search-form [name="trackNumber"]').value = '';
    page = 1;
    loadList().catch(() => {});
  });
  document.getElementById('prev-btn').addEventListener('click', () => {
    if (page > 1) { page--; loadList().catch(() => {}); }
  });
  document.getElementById('next-btn').addEventListener('click', () => {
    if (page < totalPages) { page++; loadList().catch(() => {}); }
  });

  loadList().catch(() => {});
})();