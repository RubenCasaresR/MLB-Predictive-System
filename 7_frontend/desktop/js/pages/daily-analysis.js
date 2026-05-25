const DailyAnalysisPage = {
  async load(container) {
    container.innerHTML = `
      <div class="page-header">
        <h2>📊 Análisis Diario</h2>
        <p>Análisis profundo de cada juego del día con predicciones, factores clave y apuestas recomendadas</p>
      </div>
      <div class="filters-bar">
        <input type="date" class="form-input" id="analysis-date" value="${new Date().toISOString().split('T')[0]}">
        <button class="btn btn-primary" id="btn-load-analysis">Actualizar</button>
      </div>
      <div class="loading" id="analysis-loading">
        <div class="spinner"></div>
        Cargando análisis de juegos...
      </div>
      <div id="analysis-content"></div>
    `;

    document.getElementById('btn-load-analysis').addEventListener('click', () => this.loadGames());
    document.getElementById('analysis-date').addEventListener('change', () => this.loadGames());

    await this.loadGames();
  },

  async loadGames() {
    const loading = document.getElementById('analysis-loading');
    const content = document.getElementById('analysis-content');
    const date = document.getElementById('analysis-date').value;

    loading.style.display = 'flex';
    content.innerHTML = '';

    try {
      const data = await api.getDailyAnalysis(date);
      loading.style.display = 'none';

      if (!data || !data.games || data.games.length === 0) {
        content.innerHTML = '<div class="empty-state"><div class="empty-icon">📅</div><p>No hay juegos programados para esta fecha</p></div>';
        return;
      }

      this.renderGames(content, data);
    } catch (err) {
      loading.style.display = 'none';
      content.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Error al cargar: ${err.message}</p></div>`;
    }
  },

  renderGames(container, data) {
    let html = `
      <div class="stats-grid" style="margin-bottom:16px">
        <div class="stat-card">
          <div class="stat-label">Fecha</div>
          <div class="stat-value">${data.game_date}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Juegos Analizados</div>
          <div class="stat-value">${data.total_games}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Actualizado</div>
          <div class="stat-value" style="font-size:0.9rem">${api.formatDateTZ(data.generated_at)}</div>
        </div>
      </div>
    `;

    data.games.forEach((game, idx) => {
      html += this.renderGameCard(game, idx);
    });

    container.innerHTML = html;

    container.querySelectorAll('.analysis-toggle').forEach(btn => {
      btn.addEventListener('click', function () {
        const target = document.getElementById(this.dataset.target);
        const isHidden = target.style.display === 'none';
        target.style.display = isHidden ? 'block' : 'none';
        this.textContent = isHidden ? '▲ Ocultar Análisis' : '▼ Ver Análisis Completo';
      });
    });

    container.querySelectorAll('.props-toggle').forEach(btn => {
      btn.addEventListener('click', function () {
        const target = document.getElementById(this.dataset.target);
        const isHidden = target.style.display === 'none';
        target.style.display = isHidden ? 'block' : 'none';
        this.textContent = isHidden ? '▲ Ocultar Props' : '▼ Props de Jugadores';
      });
    });
  },

  renderGameCard(game, idx) {
    const hasSim = game.home_win_prob > 0 || game.away_win_prob > 0;
    const favWinPct = hasSim ? (Math.max(game.home_win_prob, game.away_win_prob) * 100).toFixed(0) : '—';
    const underWinPct = hasSim ? (Math.min(game.home_win_prob, game.away_win_prob) * 100).toFixed(0) : '—';
    const favTeam = game.home_win_prob >= game.away_win_prob || !hasSim ? game.home_team_id : game.away_team_id;
    const underTeam = game.home_win_prob >= game.away_win_prob || !hasSim ? game.away_team_id : game.home_team_id;
    const favFull = game.home_win_prob >= game.away_win_prob || !hasSim ? game.home_team_name : game.away_team_name;
    const underFull = game.home_win_prob >= game.away_win_prob || !hasSim ? game.away_team_name : game.home_team_name;

    const rec = game.recommended_bet;
    const hasRec = rec && rec.edge_pct > 0;

    const confBadge = hasRec
      ? (rec.confidence === 'Alta' ? 'badge-green' : rec.confidence === 'Media' ? 'badge-yellow' : 'badge-gray')
      : '';

    const favLogo = api.getTeamLogoHtml(favTeam);
    const underLogo = api.getTeamLogoHtml(underTeam);

    const analysisId = `analysis-${idx}`;
    const propsId = `props-${idx}`;
    const hasProps = game.props && game.props.length > 0;

    const matchupHtml = hasSim ? `
      <div class="analysis-matchup">
        <div class="analysis-team">
          ${favLogo}
          <span class="analysis-team-name">${favTeam}</span>
          <span class="analysis-team-full">${favFull}</span>
          <span class="analysis-win-pct text-green">${favWinPct}%</span>
        </div>
        <div class="analysis-vs">
          <span class="analysis-vs-text">VS</span>
          <span class="analysis-time">${api.formatTimeTZ(game.start_time)}</span>
        </div>
        <div class="analysis-team">
          ${underLogo}
          <span class="analysis-team-name">${underTeam}</span>
          <span class="analysis-team-full">${underFull}</span>
          <span class="analysis-win-pct text-red">${underWinPct}%</span>
        </div>
      </div>
      <div class="analysis-predicted-score">
        Score estimado: <strong>${favTeam} ${game.mean_home_runs.toFixed(1)} - ${game.mean_away_runs.toFixed(1)} ${underTeam}</strong>
        &nbsp;|&nbsp; Total: <strong>${game.predicted_total.toFixed(1)}</strong>
      </div>
    ` : `
      <div class="analysis-matchup">
        <div class="analysis-team">
          ${favLogo}
          <span class="analysis-team-name">${favTeam}</span>
          <span class="analysis-team-full">${favFull}</span>
          <span class="analysis-win-pct text-muted">${favWinPct}</span>
        </div>
        <div class="analysis-vs">
          <span class="analysis-vs-text">VS</span>
          <span class="analysis-time">${api.formatTimeTZ(game.start_time)}</span>
        </div>
        <div class="analysis-team">
          ${underLogo}
          <span class="analysis-team-name">${underTeam}</span>
          <span class="analysis-team-full">${underFull}</span>
          <span class="analysis-win-pct text-muted">${underWinPct}</span>
        </div>
      </div>
      <div class="analysis-predicted-score text-muted">
        Simulación no disponible — los datos se cargarán cuando el ETL procese el schedule
      </div>
    `;

    return `
      <div class="card analysis-card" style="margin-bottom:16px">
        <div class="analysis-card-header">
          ${matchupHtml}
        </div>

        ${hasRec ? `
          <div class="analysis-rec-banner ${rec.confidence === 'Alta' ? 'rec-high' : rec.confidence === 'Media' ? 'rec-med' : 'rec-low'}">
            <div class="rec-left">
              <span class="rec-label">🎯 Apuesta Recomendada</span>
              <span class="rec-team">${api.getTeamLogoHtml(rec.team)} ${rec.team}</span>
              <span class="rec-market">Moneyline (${api.formatOdds(rec.odds)})</span>
            </div>
            <div class="rec-right">
              <span class="rec-edge">Edge: <strong>${rec.edge_pct}%</strong></span>
              <span class="badge ${confBadge}">${rec.confidence}</span>
              ${rec.recommended_stake ? `<span class="rec-stake">Stake: ${api.formatCurrency(rec.recommended_stake)}</span>` : ''}
            </div>
          </div>
          ${rec.reasoning && rec.reasoning.length > 0 ? `
            <div class="analysis-rec-reasons">
              ${rec.reasoning.map(r => `<div class="rec-reason">• ${r}</div>`).join('')}
            </div>
          ` : ''}
        ` : ''}

        ${hasSim ? `
        <div class="analysis-body">
          <div class="analysis-grid">
            <div class="analysis-section">
              <div class="analysis-section-title">Lanzadores</div>
              <div class="analysis-pitcher">
                <div class="pitcher-side"><strong>${game.home_team_id}</strong> ${game.pitching_home.summary}</div>
                <div class="pitcher-side"><strong>${game.away_team_id}</strong> ${game.pitching_away.summary}</div>
              </div>
            </div>
            <div class="analysis-section">
              <div class="analysis-section-title">Ofensiva</div>
              <div class="analysis-team-stats">
                <div class="team-stat-line"><strong>${game.home_team_id}:</strong> ${game.offensive_home.summary}</div>
                <div class="team-stat-line"><strong>${game.away_team_id}:</strong> ${game.offensive_away.summary}</div>
              </div>
            </div>
          </div>

          <div class="analysis-grid">
            <div class="analysis-section">
              <div class="analysis-section-title">Bullpen</div>
              <div class="bullpen-line">${game.bullpen_home.summary}</div>
              <div class="bullpen-line">${game.bullpen_away.summary}</div>
            </div>
            <div class="analysis-section">
              <div class="analysis-section-title">Clima / Parque</div>
              <div class="weather-line">${game.weather.summary}</div>
              <div class="park-line">${game.park_factors.summary}</div>
            </div>
          </div>

          ${game.market_signals.summary ? `
            <div class="analysis-section">
              <div class="analysis-section-title">Señales de Mercado</div>
              <div class="market-line">${game.market_signals.summary}</div>
            </div>
          ` : ''}
        </div>

        ${game.key_factors && game.key_factors.length > 0 ? `
          <div class="analysis-key-factors">
            <div class="analysis-section-title">Factores Clave</div>
            <div class="factors-list">
              ${game.key_factors.map(f => `<span class="factor-item">${f}</span>`).join('')}
            </div>
          </div>
        ` : ''}

        <button class="btn btn-ghost btn-sm analysis-toggle" data-target="${analysisId}">▼ Ver Análisis Completo</button>
        <div id="${analysisId}" style="display:none" class="analysis-narrative-section">
          ${game.analysis_narrative ? game.analysis_narrative.split('\n\n').map(p => `<p>${p}</p>`).join('') : '<p>Análisis no disponible</p>'}
        </div>

        ${hasProps ? `
          <button class="btn btn-ghost btn-sm props-toggle" data-target="${propsId}" style="margin-top:8px">▼ Props de Jugadores</button>
          <div id="${propsId}" style="display:none" class="props-section">
            ${this.renderProps(game.props)}
          </div>
        ` : ''}
        ` : `
        <div class="analysis-body">
          <div class="empty-state" style="padding:20px">
            <p>Este juego está programado para hoy. El análisis detallado aparecerá cuando el ETL procese los datos del schedule. Mientras tanto, puedes ver el juego en la sección <a href="#games" onclick="window.route('games')">Juegos del Día</a>.</p>
          </div>
        </div>
        `}
      </div>
    `;
  },

  renderProps(props) {
    if (!props || props.length === 0) return '';

    let html = '<div class="props-grid">';
    props.forEach(p => {
      const isOver = p.recommendation === 'over';
      const edgeClass = p.edge_pct >= 8 ? 'text-green' : p.edge_pct >= 5 ? 'text-yellow' : '';
      html += `
        <div class="prop-card card card-flat">
          <div class="prop-player">${p.player_name}</div>
          <div class="prop-type-badge badge ${p.prop_type === 'STRIKEOUTS' ? 'badge-purple' : 'badge-blue'}">${p.prop_type}</div>
          <div class="prop-line">Línea: ${p.line_value} ${isOver ? 'Over' : 'Under'}</div>
          <div class="prop-pred">Predicho: ${p.predicted_mean.toFixed(2)}</div>
          <div class="prop-edge ${edgeClass}">Edge: ${p.edge_pct}%</div>
          <div class="prop-prob">P(Over): ${(p.prob_over * 100).toFixed(1)}% / P(Under): ${(p.prob_under * 100).toFixed(1)}%</div>
        </div>
      `;
    });
    html += '</div>';
    return html;
  },
};
