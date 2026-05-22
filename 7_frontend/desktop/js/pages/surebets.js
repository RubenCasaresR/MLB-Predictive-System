const SureBetsPage = {
  showRiesgosas: false,

  async load(container) {
    container.innerHTML = `
      <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <h2>🛡️ Apuestas Seguras</h2>
          <p>Recomendaciones con análisis multi-factor: simulación, sharp money, fatiga, bullpen, clima y más</p>
        </div>
      </div>
      <div class="loading" id="surebets-loading"><div class="spinner"></div>Analizando juegos y generando recomendaciones...</div>
      <div id="surebets-content"></div>
      <div id="surebets-error" class="empty-state" style="display:none">
        <div class="empty-icon">⚠️</div>
        <p>No se pudieron generar recomendaciones en este momento</p>
        <p style="font-size:0.8rem;color:var(--text-secondary)">Verifica que haya juegos programados con datos de simulación y mercado disponibles</p>
      </div>
    `;

    try {
      const data = await api.getSureBets();
      this.render(container, data);
    } catch (err) {
      document.getElementById('surebets-loading').style.display = 'none';
      document.getElementById('surebets-error').style.display = 'block';
    }
  },

  render(container, data) {
    document.getElementById('surebets-loading').style.display = 'none';
    const content = document.getElementById('surebets-content');
    const logo = api.getTeamLogoHtml.bind(api);

    const total = data.muy_seguras.length + data.seguras.length + data.riesgosas.length;
    const ts = data.generated_at ? new Date(data.generated_at) : new Date();
    const timeStr = api.formatDateTZ(ts);

    let html = `
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
        <span class="badge badge-green" style="font-size:0.75rem">${data.muy_seguras.length} Muy Seguras</span>
        <span class="badge badge-blue" style="font-size:0.75rem">${data.seguras.length} Seguras</span>
        <span class="badge badge-yellow" style="font-size:0.75rem;cursor:pointer" id="toggle-riesgosas">${data.riesgosas.length} Riesgosas ${this.showRiesgosas ? '▲' : '▼'}</span>
        <span style="margin-left:auto;font-size:0.72rem;color:var(--text-secondary)">Actualizado: ${timeStr}</span>
      </div>
      <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:16px;padding:8px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm)">
        ✅ Factores considerados: Edge del mercado · Simulación Monte Carlo · Dinero Sharp / RLM · Fatiga de abridores · Bullpen · Días de descanso · Viaje (husos) · Clima
      </div>
    `;

    if (total === 0) {
      html += `<div class="card"><div class="card-body"><div class="empty-state"><div class="empty-icon">📊</div><p>No hay suficientes datos para generar recomendaciones hoy</p></div></div></div>`;
      content.innerHTML = html;
      return;
    }

    // Muy Seguras
    if (data.muy_seguras.length > 0) {
      html += `<div class="section-header"><h3>🏆 Muy Seguras</h3><span class="section-count">${data.muy_seguras.length} recomendaciones</span></div>`;
      html += data.muy_seguras.map(r => this._renderCard(r, 'muy-segura', logo)).join('');
    }

    // Seguras
    if (data.seguras.length > 0) {
      html += `<div class="section-header"><h3>✅ Seguras</h3><span class="section-count">${data.seguras.length} recomendaciones</span></div>`;
      html += data.seguras.map(r => this._renderCard(r, 'segura', logo)).join('');
    }

    // Riesgosas
    if (data.riesgosas.length > 0) {
      html += `<div class="section-header"><h3>⚠️ Riesgosas</h3><span class="section-count">${data.riesgosas.length} recomendaciones</span></div>`;
      html += `<div id="riesgosas-list" style="${this.showRiesgosas ? '' : 'display:none'}">`;
      html += data.riesgosas.map(r => this._renderCard(r, 'riesgosa', logo)).join('');
      html += `</div>`;
    }

    content.innerHTML = html;

    document.getElementById('toggle-riesgosas')?.addEventListener('click', () => {
      this.showRiesgosas = !this.showRiesgosas;
      const list = document.getElementById('riesgosas-list');
      if (list) list.style.display = this.showRiesgosas ? '' : 'none';
      document.getElementById('toggle-riesgosas').innerHTML = `${data.riesgosas.length} Riesgosas ${this.showRiesgosas ? '▲' : '▼'}`;
    });

    // Expand stats toggle
    document.querySelectorAll('.surebet-toggle-stats').forEach(btn => {
      btn.addEventListener('click', () => {
        const statsEl = btn.parentElement.nextElementSibling;
        if (statsEl && statsEl.classList.contains('surebet-stats')) {
          const isHidden = statsEl.style.display === 'none';
          statsEl.style.display = isHidden ? '' : 'none';
          btn.textContent = isHidden ? '▲ Ocultar estadísticas' : '▼ Ver estadísticas';
        }
      });
    });
  },

  _renderCard(r, tier, logo) {
    const tierColors = {
      'muy-segura': { border: 'var(--accent-green)', bg: 'rgba(34,197,94,0.08)', label: 'MUY SEGURA', icon: '🏆' },
      'segura': { border: 'var(--accent-blue)', bg: 'rgba(59,130,246,0.08)', label: 'SEGURA', icon: '✅' },
      'riesgosa': { border: 'var(--accent-yellow)', bg: 'rgba(234,179,8,0.08)', label: 'RIESGOSA', icon: '⚠️' },
    };
    const tc = tierColors[tier];

    const isTotal = r.market_type && r.market_type.startsWith('OVER') || r.market_type.startsWith('UNDER');
    const marketLabel = isTotal ? r.market_type : 'Moneyline';
    const teamLabel = r.recommended_team ? logo(r.recommended_team) : '';

    return `
      <div class="card surebet-card" style="border-left:4px solid ${tc.border};margin-bottom:12px">
        <div class="surebet-header" style="background:${tc.bg}">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <div class="safety-badge" style="background:${tc.border}">
              <span class="safety-score">${r.safety_score}</span>
              <span class="safety-label">${tc.icon} ${tc.label}</span>
            </div>
            <span style="font-weight:600;font-size:0.9rem">#${r.rank}</span>
            <span class="badge badge-gray">${marketLabel}</span>
          </div>
        </div>
        <div class="card-body">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <span style="font-weight:600">${logo(r.away_team)} @ ${logo(r.home_team)}</span>
            </div>
            ${teamLabel ? `<span style="font-weight:700;font-size:1rem">Apuesta: ${teamLabel} · ${api.formatOdds(r.odds)}</span>` : `<span style="font-weight:700;font-size:1rem">${marketLabel} · ${api.formatOdds(r.odds)}</span>`}
          </div>

          <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;font-size:0.82rem">
            <span>Edge: <strong class="text-green">${r.edge_pct}%</strong></span>
            ${r.win_prob != null ? `<span>Win Prob: <strong>${r.win_prob}%</strong></span>` : ''}
            ${r.key_stats?.prob_over != null ? `<span>P(Over): <strong>${r.key_stats.prob_over}%</strong></span>` : ''}
            ${r.key_stats?.prob_under != null ? `<span>P(Under): <strong>${r.key_stats.prob_under}%</strong></span>` : ''}
            ${r.key_stats?.mean_total != null ? `<span>Proy. Total: <strong>${r.key_stats.mean_total}</strong></span>` : ''}
            ${r.key_stats?.line != null ? `<span>Línea: <strong>${r.key_stats.line}</strong></span>` : ''}
          </div>

          <div class="surebet-reasons">
            ${r.reasons.map(rea => `<div class="surebet-reason">• ${rea}</div>`).join('')}
          </div>

          <div style="margin-top:10px">
            <button class="btn btn-ghost btn-sm surebet-toggle-stats">▼ Ver estadísticas</button>
          </div>

          <div class="surebet-stats" style="display:none;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
            <table style="font-size:0.78rem">
              <tbody>
                ${Object.entries(r.key_stats || {}).map(([k, v]) => {
                  if (v === null || v === undefined || v === false) return '';
                  const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                  const val = typeof v === 'boolean' ? (v ? 'Sí' : 'No') :
                             typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
                  return `<tr><td class="text-muted" style="padding:2px 8px 2px 0">${label}</td><td class="font-mono" style="padding:2px 0">${val}</td></tr>`;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }
};
