# =============================================================================
# MLB Predictive System - Makefile
# Rubén Eduardo Casares Rosales
# =============================================================================

.ONESHELL:

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
PYTHON   := python
PIP      := pip
COMPOSE  := docker-compose
PACKAGE  := mlb_predictive

.PHONY: help install lint test run docker-up docker-down clean init-db

help:
	@echo "MLB Predictive System - Comandos disponibles"
	@echo "============================================"
	@echo "make install       Instalar dependencias Python"
	@echo "make lint          Ejecutar linter (flake8 + pylint)"
	@echo "make test          Ejecutar tests unitarios"
	@echo "make test-cov      Ejecutar tests con cobertura"
	@echo "make run           Iniciar API localmente"
	@echo "make docker-up     Iniciar todos los servicios (Docker)"
	@echo "make docker-down   Detener servicios Docker"
	@echo "make init-db       Inicializar base de datos (schema)"
	@echo "make clean         Limpiar archivos temporales"
	@echo "make data-dir      Crear directorios de datos"

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
install:
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

lint:
	flake8 --max-line-length=100 --exclude=venv,.git,__pycache__ .
	pylint --disable=C0111,C0103,C0301 --ignore=venv,__pycache__ .

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test:
	$(PYTHON) -m pytest 8_tests/ -v --tb=short

test-cov:
	$(PYTHON) -m pytest 8_tests/ -v --tb=short --cov=. --cov-report=term --cov-report=html

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
run:
	$(PYTHON) -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

run-worker:
	$(PYTHON) -m etl.orchestrator --loop

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-up:
	$(COMPOSE) up -d

docker-down:
	$(COMPOSE) down

docker-build:
	$(COMPOSE) build

docker-logs:
	$(COMPOSE) logs -f

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
init-db:
	createdb -U mlb_user mlb_predictive || true
	psql -U mlb_user -d mlb_predictive -f database/schema.sql

migrate:
	alembic upgrade head

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean:
	rm -rf __pycache__ .pytest_cache htmlcov
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name *.pyc -delete

data-dir:
	mkdir -p data/statcast_raw data/weather_raw data/market_raw data/features
	mkdir -p models
	mkdir -p logs

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------
all: install lint test
	docker-build
