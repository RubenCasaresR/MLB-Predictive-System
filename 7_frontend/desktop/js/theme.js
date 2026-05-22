const theme = {
  init() {
    const saved = localStorage.getItem('mlb-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    this.updateButton(saved);

    document.getElementById('theme-toggle').addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('mlb-theme', next);
      this.updateButton(next);
    });
  },

  updateButton(theme) {
    const btn = document.getElementById('theme-toggle');
    btn.textContent = theme === 'dark' ? '☀️' : '🌙';
    btn.title = theme === 'dark' ? 'Modo claro' : 'Modo oscuro';
  }
};

document.addEventListener('DOMContentLoaded', () => theme.init());
