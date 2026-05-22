const SimulationsPage = {
  async load(container) {
    const games = await api.getGamePreview().catch(() => []);

    const params = new URLSearchParams(window.location.search);
    const preselectedGameId = params.get('game') || '';

    container.innerHTML = `
      <div class="page-header">
        <h2>Simulaciones</h2>
        <p>Resultados de simulaciones Monte Carlo por juego</p>
      </div>

      <div class="filters-bar">
        <label style="font-size:0.82rem;color:var(--text-secondary)">Seleccionar juego:</label>
        <select class="form-select" id="sim-game-select" style="min-width:250px">
          <option value="">— Selecciona un juego —</option>
          ${games.map(g => `<option value="${g.game_id}" ${g.game_id === preselectedGameId ? 'selected' : ''}>${g.away_team} @ ${g.home_team} (${api.formatTime(g.start_time)})</option>`).join('')}
        </select>
        <button class="btn btn-primary btn-sm" id="btn-load-sim">Ver Simulación</button>
        <button class="btn btn-outline btn-sm" id="btn-run-sim" style="display:none">▶ Correr Simulación</button>
      </div>

      <div id="sim-result">
        <div class="card card-flat"><div class="card-body"><div class="empty-state"><div class="empty-icon">◎</div><p>Selecciona un juego para ver la simulación</p></div></div></div>
      </div>
    `;

    const gameSelect = document.getElementById('sim-game-select');
    const loadBtn = document.getElementById('btn-load-sim');
    const runBtn = document.getElementById('btn-run-sim');
    const resultDiv = document.getElementById('sim-result');

    function showEmpty(msg) {
      resultDiv.innerHTML = `<div class="card card-flat"><div class="card-body"><div class="empty-state"><div class="empty-icon">◎</div><p>${msg}</p></div></div></div>`;
    }

    function renderSim(sim, game, source) {
      const badge = source === 'etl' ? '<span class="badge badge-green" style="font-size:0.7rem;margin-left:8px">Pre-calculada</span>' : '<span class="badge badge-blue" style="font-size:0.7rem;margin-left:8px">Bajo demanda</span>';
      const homeName = game ? game.home_team : 'Local';
      const awayName = game ? game.away_team : 'Visitante';
      resultDiv.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px">
          <div class="stat-card">
            <div class="stat-label">${homeName} Win ${_tip('win_prob')} ${badge}</div>
            <div class="stat-value text-blue">${(sim.home_win_prob * 100).toFixed(1)}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">${awayName} Win ${_tip('win_prob')}</div>
            <div class="stat-value">${(sim.away_win_prob * 100).toFixed(1)}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Carreras ${homeName}</div>
            <div class="stat-value">${sim.mean_home_runs.toFixed(2)}</div>
            <div class="stat-sub">σ ${sim.std_home_runs.toFixed(2)}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Carreras ${awayName}</div>
            <div class="stat-value">${sim.mean_away_runs.toFixed(2)}</div>
            <div class="stat-sub">σ ${sim.std_away_runs.toFixed(2)}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Extra Innings ${_tip('extra_innings')}</div>
            <div class="stat-value text-yellow">${(sim.extra_innings_prob * 100).toFixed(1)}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Walkoff ${_tip('walkoff')}</div>
            <div class="stat-value text-yellow">${(sim.walkoff_prob * 100).toFixed(1)}%</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
          <div class="card">
            <div class="card-header">Distribución de Victorias</div>
            <div class="card-body">
              <div class="chart-container"><canvas id="sim-win-chart"></canvas></div>
              <p class="chart-stat-label">Iteraciones: ${sim.n_iterations.toLocaleString()} ${sim.computed_at ? '· ' + api.formatDate(sim.computed_at) : ''}</p>
            </div>
          </div>
          <div class="card">
            <div class="card-header">Carreras Esperadas</div>
            <div class="card-body">
              <div class="chart-container"><canvas id="sim-runs-chart"></canvas></div>
              <p class="chart-stat-label">Promedio con desviación estándar</p>
            </div>
          </div>
        </div>
      `;

      // Win probability doughnut
      setTimeout(() => {
        const winCanvas = document.getElementById('sim-win-chart');
        if (winCanvas) {
          Charts.doughnut(
            [+(sim.home_win_prob * 100).toFixed(1), +(sim.away_win_prob * 100).toFixed(1)],
            [homeName, awayName],
            [Charts.colors.green, Charts.colors.blue],
            winCanvas
          );
        }
        // Expected runs bar chart
        const runsCanvas = document.getElementById('sim-runs-chart');
        if (runsCanvas) {
          Charts.verticalBar(
            [homeName, awayName],
            [{
              label: 'Carreras',
              data: [+(sim.mean_home_runs.toFixed(2)), +(sim.mean_away_runs.toFixed(2))],
              backgroundColor: [Charts.colors.green, Charts.colors.blue],
              borderRadius: 4,
            }],
            runsCanvas,
            {}
          );
        }
      }, 0);
    }

    async function loadSim(gameId) {
      resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando simulación...</div>';
      runBtn.style.display = 'none';

      try {
        const sim = await api.getSimulation(gameId);
        const game = games.find(g => g.game_id === gameId);
        renderSim(sim, game, 'etl');
      } catch (err) {
        showEmpty('Simulación no disponible para este juego');
        runBtn.style.display = 'inline-block';
      }
    }

    async function runSim(gameId) {
      const game = games.find(g => g.game_id === gameId);
      if (!game) return;

      resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p style="margin-top:12px">Ejecutando simulación Monte Carlo (10,000 iteraciones)...</p></div>';
      runBtn.style.display = 'none';

      try {
        const sim = await api.runSimulation({
          game_id: gameId,
          home_team_id: game.home_team,
          away_team_id: game.away_team,
          home_pitcher_id: game.home_pitcher_id || 0,
          away_pitcher_id: game.away_pitcher_id || 0,
          park_factor_hr: 1.0,
          n_iterations: 10000,
        });
        renderSim(sim, game, 'ondemand');
      } catch (err) {
        resultDiv.innerHTML = `<div class="card card-flat"><div class="card-body"><div class="empty-state"><div class="empty-icon">⚠️</div><p>Error al ejecutar simulación: ${err.message}</p></div></div></div>`;
        runBtn.style.display = 'inline-block';
      }
    }

    loadBtn.addEventListener('click', () => {
      const gameId = gameSelect.value;
      if (!gameId) return;
      window.history.replaceState(null, '', `#simulations?game=${gameId}`);
      loadSim(gameId);
    });

    runBtn.addEventListener('click', () => {
      const gameId = gameSelect.value;
      if (!gameId) return;
      runSim(gameId);
    });

    if (preselectedGameId && games.some(g => g.game_id === preselectedGameId)) {
      loadSim(preselectedGameId);
    }
  }
};
