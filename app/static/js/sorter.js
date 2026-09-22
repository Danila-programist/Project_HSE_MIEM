(() => {
  let page = 1, size = 20, totalPages = 1, currentTrack = '';
  let direction = 'ALL';
  let selectedId = null;

  const listBody = document.getElementById('shipments-body');
  const detailEl = document.getElementById('detail');

  async function loadList() {
    const params = new URLSearchParams({ page, size, direction });
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
    if (s.status === 'DISPATCHED') {
      actions.push(`<div class="card"><h2>Регистрация прибытия</h2>
        <div class="row"><span class="spacer"></span>
          <button class="primary" id="arrive-btn">Зарегистрировать прибытие</button>
        </div>
      </div>`);
    } else if (s.status === 'ARRIVED') {
      actions.push(`<div class="card"><h2>Отправка в следующий узел</h2>
        <label>Следующий узел<select id="next-node"></select></label>
        <div class="row"><span class="spacer"></span>
          <button class="primary" id="dispatch-btn">Отправить в следующий узел</button>
        </div>
      </div>`);
    }

    detailEl.innerHTML = `
      <h2 style="margin:0 0 10px">${escapeHtml(s.trackNumber)}</h2>
      <div class="status-banner"><div class="status-name">${escapeHtml(s.statusName)}</div></div>
      <dl class="kv">
        <dt>Тип</dt><dd>${escapeHtml(s.shipmentType.name)}</dd>
        <dt>Габариты</dt><dd>${s.weightKg} кг · ${s.lengthCm} × ${s.widthCm} × ${s.heightCm} см</dd>
        <dt>Пункт приёма</dt><dd>${escapeHtml(s.originNode.name)}</dd>
        <dt>Пункт назначения</dt><dd>${escapeHtml(s.destinationNode.name)}</dd>
        <dt>Текущий узел</dt><dd>${escapeHtml(s.currentNode.name)}</dd>
        <dt>Следующий узел</dt><dd>${escapeHtml(s.nextNode ? s.nextNode.name : '—')}</dd>
        <dt>Создано</dt><dd>${fmtDate(s.createdAt)}</dd>
      </dl>
      ${actions.join('')}
    `;

    if (document.getElementById('arrive-btn')) wireArrive(s.id);
    if (document.getElementById('dispatch-btn')) wireDispatch(s.id, s);
  }

  function wireArrive(id) {
    document.getElementById('arrive-btn').addEventListener('click', async () => {
      try {
        const s = await api('POST', `/shipments/${id}/arrive`);
        renderCard(s);
        loadList().catch(() => {});
        toast('Прибытие зарегистрировано');
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

  document.getElementById('search-form').addEventListener('submit', (e) => {
    e.preventDefault();
    currentTrack = e.target.trackNumber.value.trim();
    page = 1;
    loadList().catch(() => {});
  });
  document.querySelectorAll('[name="direction"]').forEach((el) => {
    el.addEventListener('change', () => { direction = el.value; page = 1; loadList().catch(() => {}); });
  });
  document.getElementById('prev-btn').addEventListener('click', () => {
    if (page > 1) { page--; loadList().catch(() => {}); }
  });
  document.getElementById('next-btn').addEventListener('click', () => {
    if (page < totalPages) { page++; loadList().catch(() => {}); }
  });

  loadList().catch(() => {});
})();