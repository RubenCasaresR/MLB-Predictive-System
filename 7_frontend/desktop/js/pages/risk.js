const RiskPage = {
  async load(container) {
    const [bankroll, limits, exposure] = await Promise.all([
      api.getBankroll().catch(() => null),
      api.getRiskLimits().catch(() => null),
      api.getExposureSummary().catch(() => null),
    ]);

    const exposureEntries = exposure ? Object.entries(exposure.by_sportsbook || {}) : [];
    const gameExposure = exposure ? Object.entries(exposure.by_game || {}) : [];

    container.innerHTML = `
      <div class="page-header">
        <h2>Gestión de Riesgo</h2>
        <p>Bankroll, límites y exposición</p>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div class="card">
          <div class="card-header">Bankroll</div>
          <div class="card-body">
            ${bankroll ? `
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                  <div class="stat-label">Inicial</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(bankroll.initial)}</div>
                </div>
                <div>
                  <div class="stat-label">Actual</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(bankroll.current)}</div>
                </div>
                <div>
                  <div class="stat-label">Pico</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(bankroll.peak)}</div>
                </div>
                <div>
                  <div class="stat-label">Drawdown</div>
                  <div class="font-mono text-yellow" style="font-size:1.1rem">${bankroll.drawdown_pct.toFixed(1)}%</div>
                </div>
              </div>
              <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                  <div class="stat-label">Total Apostado</div>
                  <div class="font-mono">${api.formatCurrency(bankroll.total_wagered)}</div>
                </div>
                <div>
                  <div class="stat-label">Profit Total</div>
                  <div class="font-mono ${bankroll.total_profit >= 0 ? 'text-green' : 'text-red'}">${bankroll.total_profit >= 0 ? '+' : ''}${api.formatCurrency(bankroll.total_profit)}</div>
                </div>
                <div>
                  <div class="stat-label">ROI</div>
                  <div class="font-mono ${bankroll.roi_pct >= 0 ? 'text-green' : 'text-red'}">${bankroll.roi_pct >= 0 ? '+' : ''}${bankroll.roi_pct.toFixed(1)}%</div>
                </div>
                <div>
                  <div class="stat-label">Sharpe</div>
                  <div class="font-mono">${bankroll.sharpe_ratio ? bankroll.sharpe_ratio.toFixed(2) : '---'}</div>
                </div>
              </div>
            ` : '<div class="text-muted">No disponible</div>'}
          </div>
        </div>

        <div class="card">
          <div class="card-header">Límites de Riesgo</div>
          <div class="card-body">
            ${limits ? `
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                  <div class="stat-label">Max por Apuesta</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(limits.max_per_bet)}</div>
                </div>
                <div>
                  <div class="stat-label">Max por Día</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(limits.max_per_day)}</div>
                </div>
                <div>
                  <div class="stat-label">Max por Semana</div>
                  <div class="font-mono" style="font-size:1.1rem">${api.formatCurrency(limits.max_per_week)}</div>
                </div>
                <div>
                  <div class="stat-label">Max Drawdown</div>
                  <div class="font-mono text-yellow" style="font-size:1.1rem">${(limits.max_drawdown * 100).toFixed(0)}%</div>
                </div>
                <div>
                  <div class="stat-label">Apuestas Concurrentes</div>
                  <div class="font-mono" style="font-size:1.1rem">${limits.max_concurrent_bets}</div>
                </div>
              </div>
            ` : '<div class="text-muted">No disponible</div>'}
          </div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <div class="card-header">Exposición por Casa de Apuestas ${_tip('exposure')}</div>
          <div class="card-body compact" style="padding:0">
            ${exposureEntries.length === 0 ? '<div class="text-muted" style="padding:16px">Sin exposición actual</div>' : `
              <div class="chart-container chart-container-sm"><canvas id="risk-exposure-chart"></canvas></div>
              <table>
                <thead>
                  <tr>
                    <th>Casa</th>
                    <th class="text-right">Expuesto</th>
                  </tr>
                </thead>
                <tbody>
                  ${exposureEntries.map(([book, amount]) => `
                    <tr>
                      <td>${book}</td>
                      <td class="text-right font-mono">${api.formatCurrency(amount)}</td>
                    </tr>
                  `).join('')}
                  ${exposure ? `
                    <tr style="font-weight:600">
                      <td>Total</td>
                      <td class="text-right font-mono">${api.formatCurrency(exposure.total_exposed)}</td>
                    </tr>
                  ` : ''}
                </tbody>
              </table>
            `}
          </div>
        </div>

        <div class="card">
          <div class="card-header">Exposición por Juego ${_tip('exposure')}</div>
          <div class="card-body compact" style="padding:0">
            ${gameExposure.length === 0 ? '<div class="text-muted" style="padding:16px">Sin exposición actual</div>' : `
              <div class="chart-container chart-container-sm"><canvas id="risk-game-chart"></canvas></div>
              <table>
                <thead>
                  <tr>
                    <th>Juego</th>
                    <th class="text-right">Expuesto</th>
                  </tr>
                </thead>
                <tbody>
                  ${gameExposure.slice(0, 10).map(([game, amount]) => `
                    <tr>
                      <td class="text-muted" style="font-size:0.8rem">${game}</td>
                      <td class="text-right font-mono">${api.formatCurrency(amount)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            `}
          </div>
        </div>
      </div>
    `;

    // Exposure pie chart
    if (exposureEntries.length > 0) {
      setTimeout(() => {
        const canvas = document.getElementById('risk-exposure-chart');
        if (canvas) {
          const colors = [Charts.colors.blue, Charts.colors.green, Charts.colors.yellow, Charts.colors.red, Charts.colors.purple, Charts.colors.orange, Charts.colors.teal];
          Charts.doughnut(
            exposureEntries.map(([, v]) => v),
            exposureEntries.map(([k]) => k),
            exposureEntries.map((_, i) => colors[i % colors.length]),
            canvas
          );
        }
      }, 0);
    }

    // Game exposure horizontal bar
    if (gameExposure.length > 0) {
      setTimeout(() => {
        const canvas = document.getElementById('risk-game-chart');
        if (canvas) {
          const topGames = gameExposure.slice(0, 8);
          Charts.horizontalBar(
            topGames.map(([g]) => g.slice(0, 12)),
            topGames.map(([, v]) => v),
            Charts.colors.orange,
            canvas,
            { prefix: '$' }
          );
        }
      }, 0);
    }
  }
};
