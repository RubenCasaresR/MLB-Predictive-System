const HistoryPage = {
  async load(container) {
    const history = await api.getBetHistory(100).catch(() => []);

    const totalProfit = history.reduce((s, b) => s + (b.profit_loss || 0), 0);
    const won = history.filter(b => b.won === true).length;
    const lost = history.filter(b => b.won === false).length;
    const pending = history.filter(b => b.won === null).length;
    const winRate = won + lost > 0 ? (won / (won + lost)) : 0;

    container.innerHTML = `
      <div class="page-header">
        <h2>Historial de Apuestas</h2>
        <p>Registro completo de apuestas con resultados</p>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Total Apuestas</div>
          <div class="stat-value">${history.length}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Ganadas</div>
          <div class="stat-value text-green">${won}</div>
          <div class="stat-sub">${(winRate * 100).toFixed(1)}% win rate</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Perdidas</div>
          <div class="stat-value text-red">${lost}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pendientes</div>
          <div class="stat-value text-yellow">${pending}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Profit/Loss</div>
          <div class="stat-value ${totalProfit >= 0 ? 'text-green' : 'text-red'}">${totalProfit >= 0 ? '+' : ''}${api.formatCurrency(totalProfit)}</div>
        </div>
      </div>

      ${history.length === 0 ? '<div class="card card-flat"><div class="card-body"><div class="empty-state"><div class="empty-icon">📋</div><p>No hay historial de apuestas</p></div></div></div>' : `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
          <div class="card">
            <div class="card-header">Resultados</div>
            <div class="card-body">
              <div class="chart-container"><canvas id="history-result-chart"></canvas></div>
            </div>
          </div>
          <div class="card">
            <div class="card-header">Profit / Loss</div>
            <div class="card-body">
              <div class="chart-container"><canvas id="history-pl-chart"></canvas></div>
              <p class="chart-stat-label">Ganado: ${api.formatCurrency(history.filter(b => b.profit_loss > 0).reduce((s, b) => s + (b.profit_loss || 0), 0))} · Perdido: ${api.formatCurrency(Math.abs(history.filter(b => b.profit_loss < 0).reduce((s, b) => s + (b.profit_loss || 0), 0)))}</p>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Juego</th>
                  <th>Equipo</th>
                  <th>Mercado</th>
                  <th class="text-right">Odds</th>
                  <th class="text-right">Stake ${_tip('stake')}</th>
                  <th class="text-right">Edge ${_tip('edge')}</th>
                  <th class="text-right">Kelly ${_tip('kelly')}</th>
                  <th class="text-center">Resultado</th>
                  <th class="text-right">P/L</th>
                </tr>
              </thead>
              <tbody>
                ${history.map(b => `
                  <tr>
                    <td class="text-muted" style="font-size:0.8rem">${api.formatDate(b.placed_at)}</td>
                    <td class="text-muted" style="font-size:0.8rem">${b.game_id}</td>
                    <td><strong>${b.team}</strong></td>
                    <td class="text-muted">${b.market_type}</td>
                    <td class="text-right font-mono ${b.odds > 0 ? 'text-green' : 'text-red'}">${api.formatOdds(b.odds)}</td>
                    <td class="text-right font-mono">${api.formatCurrency(b.stake)}</td>
                    <td class="text-right font-mono text-green">${b.edge ? api.formatPercent(b.edge) : '---'}</td>
                    <td class="text-right font-mono">${b.kelly_pct ? api.formatPercent(b.kelly_pct) : '---'}</td>
                    <td class="text-center">
                      ${b.won === true ? '<span class="badge badge-green">Ganada</span>' : b.won === false ? '<span class="badge badge-red">Perdida</span>' : '<span class="badge badge-gray">Pendiente</span>'}
                    </td>
                    <td class="text-right font-mono ${b.profit_loss > 0 ? 'text-green' : b.profit_loss < 0 ? 'text-red' : ''}">${b.profit_loss ? (b.profit_loss > 0 ? '+' : '') + api.formatCurrency(b.profit_loss) : '---'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `}
    `;

    // Win/Loss doughnut
    if (won + lost > 0) {
      setTimeout(() => {
        const resultCanvas = document.getElementById('history-result-chart');
        if (resultCanvas) {
          Charts.doughnut(
            [won, lost],
            ['Ganadas', 'Perdidas'],
            [Charts.colors.green, Charts.colors.red],
            resultCanvas
          );
        }
      }, 0);
    }

    // Profit/Loss bar
    if (history.length > 0) {
      setTimeout(() => {
        const plCanvas = document.getElementById('history-pl-chart');
        if (plCanvas) {
          const pos = history.filter(b => b.profit_loss > 0).reduce((s, b) => s + (b.profit_loss || 0), 0);
          const neg = Math.abs(history.filter(b => b.profit_loss < 0).reduce((s, b) => s + (b.profit_loss || 0), 0));
          Charts.verticalBar(
            ['Profit / Loss'],
            [{
              label: 'Ganado',
              data: [pos],
              backgroundColor: Charts.colors.green,
            }, {
              label: 'Perdido',
              data: [neg],
              backgroundColor: Charts.colors.red,
            }],
            plCanvas,
            { stacked: true }
          );
        }
      }, 0);
    }
  }
};
