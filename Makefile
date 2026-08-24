# Makefile for Globexa CRM Development

.PHONY: help install dev-install test lint format typecheck db-upgrade db-downgrade db-revision db-current run-api run-worker run-beat run-flower docker-up docker-down docker-logs clean

# Default target
help:
	@echo "Globexa CRM - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install       Install production dependencies"
	@echo "  dev-install   Install development dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint          Run ruff linter"
	@echo "  format        Format code with ruff"
	@echo "  typecheck     Run mypy type checker"
	@echo ""
	@echo "Testing:"
	@echo "  test          Run all tests"
	@echo "  test-cov      Run tests with coverage"
	@echo ""
	@echo "Database:"
	@echo "  db-upgrade    Run Alembic migrations (upgrade)"
	@echo "  db-downgrade  Run Alembic migrations (downgrade)"
	@echo "  db-revision   Create new migration revision"
	@echo "  db-current    Show current migration revision"
	@echo ""
	@echo "Development Servers:"
	@echo "  run-api       Run FastAPI development server"
	@echo "  run-worker    Run Celery worker"
	@echo "  run-beat      Run Celery beat scheduler"
	@echo "  run-flower    Run Flower monitoring"
	@echo ""
	@echo "Docker:"
	@echo "  docker-up     Start all services with docker-compose"
	@echo "  docker-down   Stop all services"
	@echo "  docker-logs   View docker-compose logs"
	@echo ""
	@echo "Utilities:"
	@echo "  clean         Clean up cache and build artifacts"

# Installation
install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

# Code Quality
lint:
	ruff check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy app/

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# Database
db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-revision:
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

db-current:
	alembic current

# Development Servers
run-api:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	celery -A app.workers.celery_app worker --loglevel=info --queues=emails,campaigns,ai,integrations,usage

run-beat:
	celery -A app.workers.celery_app beat --loglevel=info

run-flower:
	celery -A app.workers.celery_app flower --port=5555

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-build:
	docker-compose build

# Clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info 2>/dev/null || true

# Full development setup
dev-setup: dev-install db-upgrade
	@echo "Development environment ready!"
	@echo "Run 'make run-api' to start the API server"
	@echo "Run 'make run-worker' to start the Celery worker"
	@echo "Run 'make run-beat' to start the Celery beat scheduler"