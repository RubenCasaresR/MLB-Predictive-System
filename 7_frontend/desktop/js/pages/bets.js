const BetsPage = {
  currentMinEdge: 0.02,
  currentLimit: 50,

  async load(container) {
    const bets = await api.getApprovedBets(this.currentMinEdge, this.currentLimit).catch(() => []);

    container.innerHTML = `
      <div class="page-header">
        <h2>Apuestas EV+</h2>
        <p>Oportunidades de valor esperado positivo</p>
      </div>

      <div class="filters-bar">
        <label style="font-size:0.82rem;color:var(--text-secondary)">Edge mínimo:</label>
        <select class="form-select" id="filter-edge" style="min-width:100px">
          <option value="0.01">1%</option>
          <option value="0.02" ${this.currentMinEdge === 0.02 ? 'selected' : ''}>2%</option>
          <option value="0.03">3%</option>
          <option value="0.05">5%</option>
          <option value="0.10">10%</option>
        </select>
        <label style="font-size:0.82rem;color:var(--text-secondary)">Límite:</label>
        <select class="form-select" id="filter-limit" style="min-width:80px">
          <option value="10">10</option>
          <option value="25">25</option>
          <option value="50" ${this.currentLimit === 50 ? 'selected' : ''}>50</option>
          <option value="100">100</option>
        </select>
        <button class="btn btn-primary btn-sm" id="btn-apply-filters">Aplicar</button>
        <span style="margin-left:auto;font-size:0.82rem;color:var(--text-secondary)">${bets.length} resultados</span>
      </div>

      ${bets.length === 0 ? '<div class="card card-flat"><div class="card-body"><div class="empty-state"><div class="empty-icon">📊</div><p>No hay oportunidades EV+ en este momento</p></div></div></div>' : `
        <div class="card">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Juego</th>
                  <th>Equipo</th>
                  <th>Casa</th>
                  <th>Mercado</th>
                  <th class="text-right">Odds</th>
                  <th class="text-right">Edge ${_tip('edge')}</th>
                  <th class="text-right">Kelly ${_tip('kelly')}</th>
                  <th class="text-right">Stake ${_tip('stake')}</th>
                  <th class="text-right">Confianza ${_tip('confidence')}</th>
                </tr>
              </thead>
              <tbody>
                ${bets.map(b => `
                  <tr>
                    <td class="text-muted" style="font-size:0.8rem">${b.game_id}</td>
                    <td><strong>${b.team}</strong></td>
                    <td class="text-muted">${b.sportsbook}</td>
                    <td class="text-muted">${b.market_type}</td>
                    <td class="text-right font-mono ${b.odds > 0 ? 'text-green' : 'text-red'}">${api.formatOdds(b.odds)}</td>
                    <td class="text-right font-mono text-green">${api.formatPercent(b.edge)}</td>
                    <td class="text-right font-mono">${api.formatPercent(b.kelly_fraction)}</td>
                    <td class="text-right font-mono">${api.formatCurrency(b.recommended_stake)}</td>
                    <td class="text-right font-mono ${b.confidence >= 0.7 ? 'text-green' : 'text-yellow'}">${api.formatPercent(b.confidence)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `}
    `;

    document.getElementById('btn-apply-filters').addEventListener('click', () => {
      this.currentMinEdge = parseFloat(document.getElementById('filter-edge').value);
      this.currentLimit = parseInt(document.getElementById('filter-limit').value);
      BetsPage.load(document.getElementById('main-content'));
    });
  }
};
