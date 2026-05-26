const LoginPage = {
  _activeTab: 'login',

  async load(container) {
    container.innerHTML = `
      <div style="display:flex;justify-content:center;align-items:center;min-height:60vh">
        <div class="card" style="width:100%;max-width:420px">
          <div class="card-header" style="text-align:center;border:none;padding-bottom:0">
            <h2>MLB Predictive</h2>
            <p style="color:var(--text-secondary);font-size:0.82rem">Inicia sesión para continuar</p>
          </div>
          <div class="card-body">
            <div style="display:flex;gap:0;margin-bottom:16px;border-radius:6px;overflow:hidden;border:1px solid var(--border-color)">
              <button class="auth-tab" data-tab="login" style="flex:1;padding:8px;border:none;cursor:pointer;font-size:0.85rem;background:var(--bg-secondary);color:var(--text-secondary)">Iniciar Sesión</button>
              <button class="auth-tab" data-tab="register" style="flex:1;padding:8px;border:none;cursor:pointer;font-size:0.85rem;background:var(--bg-secondary);color:var(--text-secondary)">Crear Cuenta</button>
            </div>

            <div id="auth-login-form">
              <div class="form-group">
                <label>Usuario</label>
                <input type="text" class="form-input" id="login-username" placeholder="username" autocomplete="username">
              </div>
              <div class="form-group">
                <label>Contraseña</label>
                <input type="password" class="form-input" id="login-password" placeholder="••••••••" autocomplete="current-password">
              </div>
              <button class="btn btn-primary" style="width:100%" id="btn-login">Iniciar Sesión</button>
            </div>

            <div id="auth-register-form" style="display:none">
              <div class="form-group">
                <label>Usuario</label>
                <input type="text" class="form-input" id="reg-username" placeholder="username" autocomplete="username">
              </div>
              <div class="form-group">
                <label>Contraseña</label>
                <input type="password" class="form-input" id="reg-password" placeholder="••••••••" autocomplete="new-password">
              </div>
              <div class="form-group">
                <label>Confirmar Contraseña</label>
                <input type="password" class="form-input" id="reg-password2" placeholder="••••••••" autocomplete="new-password">
              </div>
              <button class="btn btn-primary" style="width:100%" id="btn-register">Crear Cuenta</button>
            </div>

            <div id="auth-error" style="margin-top:12px;text-align:center;font-size:0.85rem;color:var(--accent-red)"></div>
          </div>
        </div>
      </div>
    `;

    this._activeTab = 'login';
    this._updateTabs();

    document.querySelectorAll('.auth-tab').forEach(el => {
      el.addEventListener('click', () => {
        this._activeTab = el.dataset.tab;
        this._updateTabs();
      });
    });

    document.getElementById('btn-login').addEventListener('click', () => this._handleLogin());
    document.getElementById('login-password').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._handleLogin();
    });
    document.getElementById('btn-register').addEventListener('click', () => this._handleRegister());
    document.getElementById('reg-password2').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._handleRegister();
    });
  },

  _updateTabs() {
    document.querySelectorAll('.auth-tab').forEach(el => {
      const active = el.dataset.tab === this._activeTab;
      el.style.background = active ? 'var(--accent-blue)' : 'var(--bg-secondary)';
      el.style.color = active ? '#fff' : 'var(--text-secondary)';
      el.style.fontWeight = active ? '600' : '400';
    });
    document.getElementById('auth-login-form').style.display = this._activeTab === 'login' ? 'block' : 'none';
    document.getElementById('auth-register-form').style.display = this._activeTab === 'register' ? 'block' : 'none';
    document.getElementById('auth-error').textContent = '';
  },

  _setError(msg) {
    document.getElementById('auth-error').textContent = msg;
  },

  async _handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    if (!username || !password) {
      this._setError('Completa todos los campos');
      return;
    }

    const btn = document.getElementById('btn-login');
    btn.disabled = true;
    btn.textContent = 'Iniciando sesión...';
    this._setError('');

    try {
      await api.login(username, password);
      window.location.hash = 'dashboard';
    } catch (err) {
      this._setError(err.message);
      btn.disabled = false;
      btn.textContent = 'Iniciar Sesión';
    }
  },

  async _handleRegister() {
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    const password2 = document.getElementById('reg-password2').value;
    if (!username || !password || !password2) {
      this._setError('Completa todos los campos');
      return;
    }
    if (password !== password2) {
      this._setError('Las contraseñas no coinciden');
      return;
    }
    if (password.length < 6) {
      this._setError('La contraseña debe tener al menos 6 caracteres');
      return;
    }

    const btn = document.getElementById('btn-register');
    btn.disabled = true;
    btn.textContent = 'Creando cuenta...';
    this._setError('');

    try {
      await api.register(username, password);
      window.location.hash = 'dashboard';
    } catch (err) {
      this._setError(err.message);
      btn.disabled = false;
      btn.textContent = 'Crear Cuenta';
    }
  },
};
