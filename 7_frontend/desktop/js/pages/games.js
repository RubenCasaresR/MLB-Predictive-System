const GamesPage = {
  async load(container) {
    let games = await api.getGamePreview().catch(() => null);
    let isLive = false;

    if (!games || games.length === 0) {
      games = await api.getLiveSchedule().catch(() => []);
      isLive = true;
    }

    container.innerHTML = `
      <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <h2>Juegos del Día</h2>
          <p>${isLive ? 'Datos en vivo desde MLB API' : 'Programación, líneas y predicciones'}</p>
        </div>
        ${isLive ? '<span class="badge badge-green" style="font-size:0.72rem">EN VIVO</span>' : ''}
      </div>

      ${games.length === 0 ? '<div class="card"><div class="card-body"><div class="empty-state"><div class="empty-icon">📅</div><p>No hay juegos programados para hoy</p></div></div></div>' : ''}
      ${games.map(g => {
        const isGameLive = g.is_live || g.status === 'In Progress' || g.status === 'IN_PROGRESS';
        const isFinal = g.status === 'Final' || g.status === 'FINAL';
        const showScore = isGameLive || isFinal || (g.home_score != null && g.away_score != null);
        const statusBadge = isGameLive ? 'badge-green' : isFinal ? 'badge-gray' : 'badge-blue';
        const logo = api.getTeamLogoHtml.bind(api);

        return `
        <div class="card game-card" ${g.game_id ? `onclick="App.route('simulations?game=${g.game_id}')"` : ''}>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <div class="game-time">${api.formatTimeTZ(g.start_time)}${g.venue ? ' · ' + g.venue : ''}</div>
            <span class="badge ${statusBadge}">${isGameLive ? '🔴 EN VIVO' : g.status || 'SCHEDULED'}</span>
          </div>
          <div class="game-matchup">
            <div class="team-info">
              <div class="team-name">${logo(g.away_team)}</div>
              <span class="pitcher">${g.away_pitcher_id ? 'P: ' + g.away_pitcher_id : ''}</span>
            </div>
            <div class="score-display">
              ${showScore ? `
                <div style="font-size:1.4rem;font-weight:800">${g.away_score ?? ''}</div>
                <div style="font-size:0.65rem;color:var(--text-secondary)">${isFinal ? 'FINAL' : g.inning ? g.inning + (g.inning_state === 'Top' ? '↑' : '↓') : ''}</div>
                <div style="font-size:1.4rem;font-weight:800">${g.home_score ?? ''}</div>
              ` : '<div style="font-size:1rem">vs</div>'}
            </div>
            <div class="team-info" style="text-align:right">
              <div class="team-name">${logo(g.home_team)}</div>
              <span class="pitcher">${g.home_pitcher_id ? 'P: ' + g.home_pitcher_id : ''}</span>
            </div>
          </div>
          ${!showScore ? `
          <div class="game-odds-row">
            ${g.away_moneyline ? `<span class="odds-tag">${logo(g.away_team)} <strong>${api.formatOdds(g.away_moneyline)}</strong></span>` : ''}
            ${g.home_moneyline ? `<span class="odds-tag">${logo(g.home_team)} <strong>${api.formatOdds(g.home_moneyline)}</strong></span>` : ''}
            ${g.total ? `<span class="odds-tag">O/U <strong>${g.total}</strong></span>` : ''}
          </div>
          ` : ''}
          <div class="game-signals">
            ${g.rlm_flag ? '<span class="badge badge-yellow">RLM</span>' : ''}
            ${g.sharp_money_flag ? '<span class="badge badge-purple">Sharp Money</span>' : ''}
          </div>
        </div>
      `}).join('')}

      <div class="card" id="games-chart-card" style="margin-top:16px;display:none">
        <div class="card-header">Probabilidades de Victoria</div>
        <div class="card-body">
          <div class="chart-container chart-container-lg"><canvas id="games-win-chart"></canvas></div>
        </div>
      </div>

      ${isLive && games.length > 0 ? `
        <div style="text-align:center;margin-top:12px">
          <p style="font-size:0.75rem;color:var(--text-secondary)">Datos proporcionados por <a href="https://statsapi.mlb.com" target="_blank" style="color:var(--accent-blue)">MLB Stats API</a></p>
        </div>
      ` : ''}
    `;

    // Win probability chart
    const preGame = games.filter(g => g.away_win_prob != null && !g.is_live && g.status !== 'Final' && g.status !== 'FINAL');
    if (preGame.length > 0) {
      const chartCard = document.getElementById('games-chart-card');
      chartCard.style.display = 'block';
      const canvas = document.getElementById('games-win-chart');
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
