const SettingsPage = {
  async load(container) {
    const bankroll = await api.getBankroll().catch(() => null);

    const gloss = api.glossary;

    container.innerHTML = `
      <div class="page-header">
        <h2>Configuración</h2>
        <p>Preferencias del sistema y gestión de bankroll</p>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <div class="card-header">Bankroll ${_tip('bankroll')}</div>
          <div class="card-body">
            ${bankroll ? `
              <div class="form-group">
                <label>Bankroll Actual</label>
                <div class="font-mono" style="font-size:1.2rem;margin-bottom:8px">${api.formatCurrency(bankroll.current)}</div>
              </div>
              <div class="form-group">
                <label for="new-bankroll">Nuevo Bankroll</label>
                <input type="number" class="form-input" id="new-bankroll" value="${bankroll.current}" step="100" min="100">
              </div>
              <button class="btn btn-primary" id="btn-update-bankroll">Actualizar Bankroll</button>
              <div id="bankroll-result" style="margin-top:8px"></div>
            ` : '<div class="text-muted">No se pudo cargar la información del bankroll</div>'}
          </div>
        </div>

        <div class="card">
          <div class="card-header">Acerca del Sistema</div>
          <div class="card-body">
            <div style="display:grid;gap:8px">
              <div>
                <div class="stat-label">Versión</div>
                <div>1.0.0</div>
              </div>
              <div>
                <div class="stat-label">API</div>
                <div><a href="http://localhost:8000/docs" target="_blank">Documentación API</a></div>
              </div>
              <div>
                <div class="stat-label">WebSocket</div>
                <div class="text-muted">Alertas en tiempo real: ${api.ws ? 'Conectado' : 'Desconectado'}</div>
              </div>
              <div>
                <div class="stat-label">Zona Horaria</div>
                <div class="text-muted">${api.tzLabel} (UTC-6)</div>
              </div>
              <div>
                <div class="stat-label">Tema</div>
                <div class="text-muted">${document.documentElement.getAttribute('data-theme') === 'dark' ? 'Oscuro' : 'Claro'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-header">Glosario de Términos</div>
        <div class="card-body compact" style="padding:0">
          ${Object.values(gloss).map(g => `
            <div class="glossary-term">
              <div class="term-name">${g.term}</div>
              <div class="term-def">${g.definition}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    document.getElementById('btn-update-bankroll')?.addEventListener('click', async () => {
      const input = document.getElementById('new-bankroll');
      const amount = parseFloat(input.value);
      if (isNaN(amount) || amount <= 0) {
        document.getElementById('bankroll-result').innerHTML = '<span class="text-red">Ingresa un valor válido</span>';
        return;
      }
      try {
        const result = await api.updateBankroll(amount);
        document.getElementById('bankroll-result').innerHTML = `<span class="text-green">Bankroll actualizado: ${api.formatCurrency(result.previous)} → ${api.formatCurrency(result.current)}</span>`;
      } catch (err) {
        document.getElementById('bankroll-result').innerHTML = `<span class="text-red">Error: ${err.message}</span>`;
      }
    });
  }
};
