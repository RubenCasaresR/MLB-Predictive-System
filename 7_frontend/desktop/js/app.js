const App = {
  currentPage: '',
    pageTitleMap: {
    dashboard: 'Dashboard',
    'daily-analysis': '📊 Análisis Diario',
    surebets: '🛡️ Apuestas Seguras',
    bets: 'Apuestas EV+',
    games: 'Juegos del Día',
    simulations: 'Simulaciones',
    alerts: 'Alertas',
    history: 'Historial de Apuestas',
    risk: 'Gestión de Riesgo',
    settings: 'Configuración',
    login: 'Iniciar Sesión',
  },

  init() {
    api.init();
    this.setupNav();
    this.setupRouter();
    this.setupLogout();
    window.addEventListener('hashchange', () => this.route());
    this.route();
  },

  setupNav() {
    document.querySelectorAll('[data-nav]').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('[data-nav]').forEach(n => n.classList.remove('active'));
        el.classList.add('active');
      });
    });
  },

  setupRouter() {
    window.route = (page) => { window.location.hash = page; };
  },

  setupLogout() {
    document.getElementById('btn-logout')?.addEventListener('click', () => {
      api.clearToken();
      window.location.hash = 'login';
    });
  },

  updateSidebar() {
    const loginItem = document.getElementById('nav-login');
    const userSection = document.getElementById('sidebar-user');
    const usernameEl = document.getElementById('sidebar-username');
    if (api.token) {
      if (loginItem) loginItem.style.display = 'none';
      if (userSection) userSection.style.display = 'flex';
      if (usernameEl && api.username) usernameEl.textContent = `👤 ${api.username}`;
    } else {
      if (loginItem) loginItem.style.display = 'flex';
      if (userSection) userSection.style.display = 'none';
    }
  },

  async route() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    const page = hash.split('?')[0];

    if (page !== 'login' && !api.token) {
      window.location.hash = 'login';
      return;
    }

    if (page === this.currentPage) return;
    this.currentPage = page;

    const title = this.pageTitleMap[page] || 'MLB Predictive';
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = title;

    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Cargando...</div>';

    Charts.clearAll();

    try {
      switch (page) {
        case 'dashboard': await DashboardPage.load(container); break;
        case 'daily-analysis': await DailyAnalysisPage.load(container); break;
        case 'surebets': await SureBetsPage.load(container); break;
        case 'bets': await BetsPage.load(container); break;
        case 'games': await GamesPage.load(container); break;
        case 'simulations': await SimulationsPage.load(container); break;
        case 'alerts': await AlertsPage.load(container); break;
        case 'history': await HistoryPage.load(container); break;
        case 'risk': await RiskPage.load(container); break;
        case 'settings': await SettingsPage.load(container); break;
        case 'login': await LoginPage.load(container); break;
        default:
          container.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><p>Página no encontrada</p></div>';
      }
    } catch (err) {
      console.error('Page error:', err);
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Error: ${err.message}</p></div>`;
    }

    this.updateActiveNav(page);
    this.updateSidebar();
  },

  updateActiveNav(page) {
    document.querySelectorAll('[data-nav]').forEach(el => {
      const href = el.getAttribute('href');
      el.classList.toggle('active', href === `#${page}`);
    });
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('alert-toast-container');
    const toast = document.createElement('div');
    toast.className = 'alert-toast';
    const colors = { info: 'var(--accent-blue)', success: 'var(--accent-green)', warning: 'var(--accent-yellow)', error: 'var(--accent-red)' };
    toast.style.borderLeft = `3px solid ${colors[type] || colors.info}`;
    toast.innerHTML = `<div style="font-size:0.82rem">${message}</div>`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 4000);
    toast.addEventListener('click', () => toast.remove());
  }
};

document.addEventListener('DOMContentLoaded', () => App.init());
