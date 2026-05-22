const AlertsPage = {
  currentFilter: 'all',

  async load(container) {
    const alertData = await api.getAlerts(false).catch(() => ({ alerts: [], total: 0, unread_count: 0 }));
    const alerts = alertData.alerts || [];

    container.innerHTML = `
      <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <h2>Alertas</h2>
          <p>Señales de Sharp Money, RLM y oportunidades EV+</p>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary btn-sm" id="btn-mark-all-read">Marcar todas leídas</button>
          <button class="btn btn-ghost btn-sm" id="btn-refresh-alerts">Actualizar</button>
        </div>
      </div>

      <div class="filters-bar">
        <button class="btn ${this.currentFilter === 'all' ? 'btn-primary' : 'btn-ghost'} btn-sm filter-btn" data-filter="all">Todas (${alertData.total})</button>
        <button class="btn ${this.currentFilter === 'unread' ? 'btn-primary' : 'btn-ghost'} btn-sm filter-btn" data-filter="unread">No leídas (${alertData.unread_count})</button>
      </div>

      <div class="card" id="alerts-list">
        <div class="card-body compact" style="padding:0">
          ${alerts.length === 0 ? '<div class="empty-state" style="padding:40px 20px"><div class="empty-icon">🔔</div><p>No hay alertas</p></div>' : ''}
          ${alerts.map(a => `
            <div class="alert-item ${a.is_read ? '' : 'unread'}" data-id="${a.alert_id}">
              <div class="alert-icon ${a.signal_type === 'SHARP_MONEY' ? 'badge-purple' : a.signal_type === 'RLM' ? 'badge-yellow' : 'badge-green'}" style="background:${a.is_read ? 'var(--bg-hover)' : 'var(--bg-card)'}">
                ${a.signal_type === 'SHARP_MONEY' ? '📈' : a.signal_type === 'RLM' ? '📊' : '💰'}
              </div>
              <div class="alert-content">
                <div class="alert-message">${a.message}</div>
                <div class="alert-meta">${a.signal_type} · ${api.formatDate(a.created_at)}</div>
              </div>
              ${!a.is_read ? '<span class="badge badge-blue" style="flex-shrink:0">Nueva</span>' : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;

    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.currentFilter = btn.dataset.filter;
        const data = await api.getAlerts(this.currentFilter === 'unread').catch(() => ({ alerts: [] }));
        const filtered = data.alerts || [];
        const list = document.getElementById('alerts-list');
        list.innerHTML = `
          <div class="card-body compact" style="padding:0">
            ${filtered.length === 0 ? '<div class="empty-state" style="padding:40px 20px"><div class="empty-icon">🔔</div><p>No hay alertas</p></div>' : ''}
            ${filtered.map(a => `
              <div class="alert-item ${a.is_read ? '' : 'unread'}" data-id="${a.alert_id}">
                <div class="alert-icon" style="background:${a.is_read ? 'var(--bg-hover)' : 'var(--bg-card)'}">
                  ${a.signal_type === 'SHARP_MONEY' ? '📈' : a.signal_type === 'RLM' ? '📊' : '💰'}
                </div>
                <div class="alert-content">
                  <div class="alert-message">${a.message}</div>
                  <div class="alert-meta">${a.signal_type} · ${api.formatDate(a.created_at)}</div>
                </div>
                ${!a.is_read ? '<span class="badge badge-blue" style="flex-shrink:0">Nueva</span>' : ''}
              </div>
            `).join('')}
          </div>
        `;
        this.attachClickHandlers();
      });
    });

    document.getElementById('btn-mark-all-read')?.addEventListener('click', async () => {
      await api.markAllAlertsRead();
      App.showToast('Todas las alertas marcadas como leídas', 'success');
      this.load(document.getElementById('main-content'));
    });

    document.getElementById('btn-refresh-alerts')?.addEventListener('click', () => {
      this.load(document.getElementById('main-content'));
    });

    this.attachClickHandlers();
    this.setupWebSocket();
  },

  attachClickHandlers() {
    document.querySelectorAll('.alert-item').forEach(el => {
      el.addEventListener('click', async () => {
        const id = parseInt(el.dataset.id);
        if (el.classList.contains('unread')) {
          await api.markAlertRead(id);
          el.classList.remove('unread');
          el.querySelector('.badge-blue')?.remove();
        }
      });
    });
  },

  setupWebSocket() {
    api.onAlert((data) => {
      const container = document.getElementById('main-content');
      const list = container.querySelector('#alerts-list');
      if (list) {
        const unreadBadge = container.querySelector('[data-filter="unread"]');
        if (unreadBadge) {
          const match = unreadBadge.textContent.match(/(\d+)/);
          if (match) unreadBadge.textContent = `No leídas (${parseInt(match[1]) + 1})`;
        }
      }
      App.showToast(data.message || 'Nueva alerta', 'info');
    });
  }
};
