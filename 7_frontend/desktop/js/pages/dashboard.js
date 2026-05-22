const DashboardPage = {
  async load(container) {
    const [bankroll, games, bets] = await Promise.all([
      api.getBankroll().catch(() => null),
      api.getGamePreview().catch(() => null),
      api.getApprovedBets(0.02, 5).catch(() => null),
    ]);

    let liveGames = null;
    let isLive = false;
    if (!games || games.length === 0) {
      liveGames = await api.getLiveSchedule().catch(() => null);
      isLive = true;
    }

    const displayGames = (games && games.length > 0) ? games : liveGames;
    const isGamesEmpty = !displayGames || displayGames.length === 0;
    const isBetsEmpty = !bets || bets.length === 0;

    container.innerHTML = `
      <div class="page-header">
        <h2>Dashboard</h2>
        <p>Resumen general del sistema</p>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Bankroll ${_tip('bankroll')}</div>
          <div class="stat-value">${bankroll ? api.formatCurrency(bankroll.current) : '---'}</div>
          <div class="stat-sub">${bankroll ? 'Pico: ' + api.formatCurrency(bankroll.peak) : 'No disponible'}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">ROI ${_tip('roi')}</div>
          <div class="stat-value ${bankroll && bankroll.roi_pct >= 0 ? 'text-green' : 'text-red'}">${bankroll ? (bankroll.roi_pct >= 0 ? '+' : '') + bankroll.roi_pct.toFixed(1) + '%' : '---'}</div>
          <div class="stat-sub">Retorno sobre inversión</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Drawdown ${_tip('drawdown')}</div>
          <div class="stat-value text-yellow">${bankroll ? bankroll.drawdown_pct.toFixed(1) + '%' : '---'}</div>
          <div class="stat-sub">Máxima caída</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Apuestas</div>
          <div class="stat-value">${bankroll ? bankroll.bet_count : '---'}</div>
          <div class="stat-sub">Total realizadas</div>
        </div>
      </div>

      <div class="section-header">
        <h3>Juegos del Día</h3>
        <span class="section-count">${displayGames ? displayGames.length : 0} juegos${isLive ? ' · EN VIVO' : ''}</span>
      </div>
      ${isGamesEmpty ? `
        <div class="card">
          <div class="card-body" style="padding:24px">
            <div class="empty-state">
              <div class="empty-icon">📅</div>
              <p style="margin-bottom:4px">No hay juegos programados hoy</p>
              <p style="font-size:0.8rem;color:var(--text-secondary)">Intenta más tarde o verifica la conexión a MLB API</p>
            </div>
          </div>
        </div>
      ` : ''}
      ${displayGames ? displayGames.slice(0, 6).map(g => {
        const isGameLive = g.is_live || g.status === 'In Progress' || g.status === 'IN_PROGRESS';
        const isFinal = g.status === 'Final' || g.status === 'FINAL';
        const showScore = isGameLive || isFinal || (g.home_score != null && g.away_score != null);
        const hasOdds = g.away_moneyline || g.home_moneyline;

        const logo = api.getTeamLogoHtml.bind(api);
        return `
        <div class="card game-card" onclick="App.route('games')">
          <div class="game-time">${api.formatTimeTZ(g.start_time)} · ${isGameLive ? '<span class="badge badge-green">EN VIVO</span>' : g.status || 'SCHEDULED'}${g.venue ? ' · ' + g.venue : ''}</div>
          <div class="game-matchup">
            <div class="team-info">
              <div class="team-name">${logo(g.away_team)}</div>
              <span class="pitcher">${g.away_pitcher_id || ''}</span>
            </div>
            <div class="score-display" style="min-width:${showScore ? '70' : '50'}px">
              ${showScore ? `
                <div style="font-size:1.3rem;font-weight:800;line-height:1.2">${g.away_score ?? ''}</div>
                <div style="font-size:0.6rem;color:var(--text-secondary);line-height:1">${isFinal ? 'F' : isGameLive && g.inning ? g.inning + (g.inning_state === 'Top' ? '↑' : '↓') : ''}</div>
                <div style="font-size:1.3rem;font-weight:800;line-height:1.2">${g.home_score ?? ''}</div>
              ` : (g.away_win_prob != null ? `<div style="font-size:0.7rem;color:var(--text-secondary);font-weight:400">${(g.away_win_prob * 100).toFixed(0)}%</div><div>vs</div><div style="font-size:0.7rem;color:var(--text-secondary);font-weight:400">${(g.home_win_prob * 100).toFixed(0)}%</div>` : '<div>vs</div>')}
            </div>
            <div class="team-info" style="text-align:right">
              <div class="team-name">${logo(g.home_team)}</div>
              <span class="pitcher">${g.home_pitcher_id || ''}</span>
            </div>
          </div>
          ${!showScore && hasOdds ? `
          <div class="game-odds-row">
            ${g.away_moneyline ? `<span class="odds-tag">${logo(g.away_team)} ${api.formatOdds(g.away_moneyline)}</span>` : ''}
            ${g.home_moneyline ? `<span class="odds-tag">${logo(g.home_team)} ${api.formatOdds(g.home_moneyline)}</span>` : ''}
            ${g.total ? `<span class="odds-tag">O/U ${g.total}</span>` : ''}
          </div>
          ` : ''}
          <div class="game-signals">
            ${g.rlm_flag ? '<span class="badge badge-yellow">RLM</span>' : ''}
            ${g.sharp_money_flag ? '<span class="badge badge-purple">Sharp</span>' : ''}
          </div>
        </div>
      `}).join('') : ''}

      <div class="section-header">
        <h3>Apuestas EV+ ${_tip('ev')}</h3>
        <span class="section-count">${bets ? bets.length : 0} oportunidades</span>
      </div>
      ${isBetsEmpty ? `
        <div class="card">
          <div class="card-body" style="padding:24px">
            <div class="empty-state">
              <div class="empty-icon">📊</div>
              <p>No hay oportunidades EV+ en este momento</p>
              <p style="font-size:0.8rem;color:var(--text-secondary)">Las apuestas EV+ se generan cuando el sistema de simulación y odds están activos</p>
            </div>
          </div>
        </div>
      ` : ''}
      ${bets ? bets.map(b => `
        <div class="card ev-card">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="ev-team">${b.team}</span>
            <span class="ev-odds ${b.odds > 0 ? 'text-green' : 'text-red'}">${api.formatOdds(b.odds)}</span>
          </div>
          <div class="ev-details">
            <div class="ev-metric">
              <span class="metric-label">Edge ${_tip('edge')}</span>
              <span class="metric-value text-green">${api.formatPercent(b.edge)}</span>
            </div>
            <div class="ev-metric">
              <span class="metric-label">Kelly ${_tip('kelly')}</span>
              <span class="metric-value">${api.formatPercent(b.kelly_fraction)}</span>
            </div>
            <div class="ev-metric">
              <span class="metric-label">Stake ${_tip('stake')}</span>
              <span class="metric-value">${api.formatCurrency(b.recommended_stake)}</span>
            </div>
            <div class="ev-metric">
              <span class="metric-label">Confianza ${_tip('confidence')}</span>
              <span class="metric-value ${b.confidence >= 0.7 ? 'text-green' : 'text-yellow'}">${api.formatPercent(b.confidence)}</span>
            </div>
          </div>
          <div class="ev-footer">
            <span>${b.sportsbook} · ${b.market_type}</span>
            <span>${b.game_id}</span>
          </div>
        </div>
      `).join('') : ''}

      ${isLive ? `
        <div style="text-align:center;margin-top:16px">
          <p style="font-size:0.72rem;color:var(--text-secondary)">Datos de juegos: <a href="https://statsapi.mlb.com" target="_blank" style="color:var(--accent-blue)">MLB Stats API</a></p>
        </div>
      ` : ''}
    `;

    // Win probability chart for pre-game games
    const preGame = (displayGames || []).filter(g => g.away_win_prob != null && !g.is_live && g.status !== 'Final' && g.status !== 'FINAL');
    if (preGame.length > 0) {
      const chartDiv = document.createElement('div');
      chartDiv.className = 'card';
      chartDiv.innerHTML = `<div class="card-header">Probabilidades de Victoria ${_tip('win_prob')}</div>
        <div class="card-body">
          <div class="chart-container chart-container-lg"><canvas id="dash-win-chart"></canvas></div>
        </div>`;
      container.querySelector('.section-header').after(chartDiv);

      const canvas = document.getElementById('dash-win-chart');
      const labels = preGame.map(g => `${g.away_team} @ ${g.home_team}`);
      const homeData = preGame.map(g => +(g.home_win_prob * 100).toFixed(1));
      const awayData = preGame.map(g => +(g.away_win_prob * 100).toFixed(1));

      Charts.verticalBar(labels, [
        { label: 'Visitante', data: awayData, backgroundColor: Charts.colors.blue },
        { label: 'Local', data: homeData, backgroundColor: Charts.colors.green },
      ], canvas, { title: 'Probabilidad de Victoria (%)', stacked: false });
    }
  }
};
