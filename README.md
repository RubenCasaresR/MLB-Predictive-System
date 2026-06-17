# MLB Predictive System

Sistema de Análisis Predictivo y Gestión de Riesgo para MLB. Stack: **Python 3.12+, FastAPI, PostgreSQL 15+, SQLAlchemy, NumPy, CatBoost**.

## Arquitectura

```
mlb-predictive-system/
├── api/           → FastAPI REST endpoints + auth + services
├── etl/           → Ingestors (Statcast, weather, odds, lineups)
├── prediction/    → Monte Carlo simulator, feature pipeline, Poisson props
├── risk/          → Kelly criterion, bankroll management, EV calculator
├── features/      → Fatigue detector, sharp money detection
├── database/      → schema.sql, migrations, seed data
├── alembic/       → Migration history
├── 7_frontend/    → Desktop frontend (HTML/JS/CSS)
└── 8_tests/       → Pytest test suite (640+ tests)
```

## Stack

| Componente | Tecnología |
|---|---|
| API | FastAPI + Uvicorn |
| DB | PostgreSQL 15 (async: asyncpg, sync: psycopg2-binary) |
| Async driver | asyncpg (prod), aiosqlite (tests) |
| ORM | SQLAlchemy 2.0 raw SQL |
| Migrations | Alembic |
| ML | CatBoost, scikit-learn, statsmodels |
| Simulación | Monte Carlo (10K iteraciones) |
| Riesgo | Kelly Criterion (full/quarter/half) |
| Frontend | HTML/CSS/JS desktop app |
| CI | Makefile + pytest + ruff |

## Setup rápido

```bash
# Clonar
git clone <repo> && cd mlb-predictive-system

# Virtualenv
python -m venv .venv && source .venv/bin/activate  # Linux/Mac
.\.venv\Scripts\activate                             # Windows

# Instalar
pip install -e .
pip install -e ".[test]"
pip install -r requirements-dev.txt

# Configurar
cp .env.example .env   # Editar credenciales

# Inicializar DB
python database/init_db.py
alembic upgrade head

# Ejecutar
mlb-api                # API en http://localhost:8000
```

## Endpoints API

| Prefix | Auth | Descripción |
|---|---|---|
| `/api/v1/auth/register` | No | Registro de usuario |
| `/api/v1/auth/login` | No | Login (JWT) |
| `/api/v1/bets/*` | JWT | EV+, simulación, props, bet slip |
| `/api/v1/risk/*` | JWT | Bankroll, exposure check, límites |
| `/api/v1/stats/*` | No | Estadísticas, previews, MLB live data |
| `/api/v1/alerts/*` | JWT | Alertas de sharp money, WebSocket |
| `/api/v1/analysis/daily` | No | Análisis diario completo |
| `/health` | No | Health check con estado de DB/APIs |

## Testing

```bash
make test          # pytest con coverage
make test-quick    # pytest -x (fallo rápido)
make lint          # ruff check
```

Variables de entorno clave: `DATABASE_URL` (PostgreSQL), `JWT_SECRET`, `ODDS_API_KEY`, `MLB_API_KEY`.

## Licencia

Propietaria — Rubén Eduardo Casares Rosales
