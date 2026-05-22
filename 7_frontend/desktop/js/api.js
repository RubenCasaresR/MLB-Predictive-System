function _tip(key) {
  const g = api.glossary[key];
  if (!g) return '';
  return '<span class="info-tip" data-tip="' + g.definition.replace(/"/g, '&quot;') + '">?</span>';
}

const api = {
  baseUrl: 'http://localhost:8000/api/v1',
  wsUrl: 'ws://localhost:8000/api/v1/alerts/ws',
  alertCallbacks: [],
  wsReconnectTimer: null,

  async fetch(url, options = {}) {
    const res = await fetch(`${this.baseUrl}${url}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      if (res.status === 204) return null;
      const text = await res.text().catch(() => '');
      let detail;
      try { detail = JSON.parse(text).detail; } catch { detail = text || `Error ${res.status}`; }
      throw new Error(detail);
    }
    return res.json();
  },

  getBankroll() { return this.fetch('/risk/bankroll'); },

  updateBankroll(amount) { return this.fetch(`/risk/bankroll/update?new_amount=${amount}`, { method: 'POST' }); },

  getApprovedBets(minEdge = 0.02, limit = 50) { return this.fetch(`/bets/approved?min_edge=${minEdge}&limit=${limit}`); },

  getGamePreview(date) {
    const q = date ? `?date=${date}` : '';
    return this.fetch(`/stats/preview${q}`);
  },

  getGameDetail(gameId) { return this.fetch(`/stats/preview/${gameId}`); },

  getSimulation(gameId) { return this.fetch(`/bets/simulate/${gameId}`); },

  runSimulation(data) {
    return this.fetch('/bets/simulate', { method: 'POST', body: JSON.stringify(data) });
  },

  getAlerts(unreadOnly = false) { return this.fetch(`/alerts?unread_only=${unreadOnly ? 'true' : 'false'}&limit=100`); },

  markAlertRead(alertId) { return this.fetch(`/alerts/${alertId}/read`, { method: 'POST' }); },

  markAllAlertsRead() { return this.fetch('/alerts/read-all', { method: 'POST' }); },

  getBetHistory(limit = 100) { return this.fetch(`/bets/history?limit=${limit}`); },

  getRiskLimits() { return this.fetch('/risk/limits'); },

  getExposureSummary() { return this.fetch('/risk/exposure/summary'); },

  checkExposure(stake) { return this.fetch(`/risk/exposure/check?stake=${stake}`); },

  getPlayerStats(playerId) { return this.fetch(`/stats/players/${playerId}`); },

  getSharpMoneySignals(gameId) {
    const q = gameId ? `?game_id=${gameId}` : '';
    return this.fetch(`/stats/market/sharp-money${q}`);
  },

  getLiveSchedule(date) {
    const q = date ? `?date=${date}` : '';
    return this.fetch(`/stats/live/schedule${q}`);
  },

  getLiveGame(gamePk) {
    return this.fetch(`/stats/live/schedule/${gamePk}`);
  },

  onAlert(callback) {
    this.alertCallbacks.push(callback);
    if (!this.ws) this.connectWebSocket();
  },

  connectWebSocket() {
    try {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => {
        this.ws.send(JSON.stringify({ type: 'subscribe', channels: ['sharp_money', 'ev_positive', 'rlm'] }));
      };
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'alert' || data.type === 'ev_alert') {
          this.alertCallbacks.forEach(cb => cb(data));
        }
      };
      this.ws.onclose = () => {
        this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
      };
      this.ws.onerror = () => this.ws?.close();
    } catch (e) {
      console.warn('WebSocket connection failed');
      this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
    }
  },

  disconnectWebSocket() {
    if (this.wsReconnectTimer) clearTimeout(this.wsReconnectTimer);
    this.ws?.close();
    this.ws = null;
  },

  formatCurrency(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(n);
  },

  formatPercent(n) { return (n * 100).toFixed(1) + '%'; },

  formatOdds(n) { return n > 0 ? '+' + n : String(n); },

  tzLabel: 'CDMX',

  formatDate(d) {
    if (!d) return '';
    const date = new Date(d);
    return date.toLocaleDateString('es-MX', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  },

  formatTime(d) {
    if (!d) return '';
    const date = new Date(d);
    return date.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
  },

  formatTimeTZ(d) {
    if (!d) return '';
    return this.formatTime(d) + ' ' + this.tzLabel;
  },

  formatDateTZ(d) {
    if (!d) return '';
    return this.formatDate(d) + ' ' + this.tzLabel;
  },

  glossary: {
    bankroll: {
      term: 'Bankroll',
      definition: 'Capital total disponible para realizar apuestas. Es tu presupuesto de juego.',
    },
    roi: {
      term: 'ROI (Return on Investment)',
      definition: 'Retorno sobre la inversión. Mide qué tan rentables son tus apuestas en porcentaje.',
    },
    drawdown: {
      term: 'Drawdown',
      definition: 'Caída máxima del bankroll desde su punto más alto. Indica el riesgo asumido.',
    },
    ev: {
      term: 'EV (Expected Value)',
      definition: 'Valor Esperado. Una apuesta con EV+ significa que tiene una ventaja matemática sobre la casa.',
    },
    edge: {
      term: 'Edge',
      definition: 'Ventaja porcentual que tienes sobre la cuota real del evento. Edge positivo = apuesta rentable a largo plazo.',
    },
    kelly: {
      term: 'Criterio de Kelly',
      definition: 'Fórmula matemática que determina el tamaño óptimo de la apuesta según tu edge y las odds. Maximiza el crecimiento del bankroll.',
    },
    stake: {
      term: 'Stake',
      definition: 'Cantidad de dinero que se arriesga en una apuesta. Calculado según el criterio de Kelly.',
    },
    rlm: {
      term: 'RLM (Reverse Line Movement)',
      definition: 'Movimiento de línea contrario al dinero del público. Indica que apostadores profesionales (sharp money) están moviendo la línea en dirección opuesta al público general.',
    },
    sharp_money: {
      term: 'Sharp Money',
      definition: 'Dinero de apostadores profesionales o "sharp". Cuando los sharp apuestan fuerte a un lado, las líneas se mueven. Es una señal de valor oculto.',
    },
    confidence: {
      term: 'Confianza',
      definition: 'Nivel de certeza del modelo sobre esta apuesta. Basado en la consistencia de las señales (sharp money, RLM, edge).',
    },
    moneyline: {
      term: 'Moneyline',
      definition: 'Apuesta directa al ganador del partido. Odds negativas (-150) indican favorito; odds positivas (+200) indican underdog.',
    },
    over_under: {
      term: 'Over/Under (Total)',
      definition: 'Apuesta al total de carreras combinadas de ambos equipos. Over = más que el total, Under = menos que el total.',
    },
    sharpe: {
      term: 'Ratio Sharpe',
      definition: 'Mide el retorno ajustado por riesgo. Un Sharpe mayor a 1 indica buen rendimiento considerando el riesgo asumido.',
    },
    exposure: {
      term: 'Exposición',
      definition: 'Cantidad total de dinero comprometido en apuestas activas. Una alta exposición puede poner en riesgo el bankroll.',
    },
    win_prob: {
      term: 'Probabilidad de Victoria',
      definition: 'Porcentaje estimado por el modelo de simulación Monte Carlo de que un equipo gane el partido.',
    },
    extra_innings: {
      term: 'Extra Innings',
      definition: 'Probabilidad de que el juego se extienda más de 9 entradas por empate.',
    },
    walkoff: {
      term: 'Walkoff',
      definition: 'Probabilidad de que el equipo local gane el partido en su último turno al bate.',
    },
  },

  teamLogos: {
    ARI:'ARI', ATL:'ATL', BAL:'BAL', BOS:'BOS', CHC:'CHC', CHW:'CHW',
    CIN:'CIN', CLE:'CLE', COL:'COL', DET:'DET', HOU:'HOU', KC:'KC',
    KCR:'KC', LAA:'LAA', LAD:'LAD', MIA:'MIA', MIL:'MIL', MIN:'MIN',
    NYM:'NYM', NYY:'NYY', OAK:'OAK', PHI:'PHI', PIT:'PIT', SD:'SD',
    SDP:'SD', SEA:'SEA', SF:'SF', SFG:'SF', STL:'STL', TB:'TB',
    TBR:'TB', TEX:'TEX', TOR:'TOR', WSH:'WSH', WSN:'WSH',
  },

  getTeamLogoHtml(code) {
    const espnCode = this.teamLogos[code];
    if (!espnCode) return code;
    const url = `https://a.espncdn.com/i/teamlogos/mlb/500/${espnCode}.png`;
    return `<img class="team-logo" src="${url}" alt="${code}" title="${code}" loading="lazy" onerror="this.style.display='none'"> ${code}`;
  },
};
