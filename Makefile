ifneq ("$(wildcard .env)","")
	include .env
	export
endif

PYTHON := .venv/bin/python3
SCRIPTS_DIR := scripts


# Project management
.PHONY: install run migrate makemigrations shell test clean

dev:
	uv run uvicorn app.main:app --reload --port 8001

run:
	uv sync
	uv run main.py --port 18681 --host 0.0.0.0

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	rm -rf .coverage htmlcov/
	find . -path "./*" -not -path "./.venv/*" -not -path "./venv/*" -path "*/migrations/*.py" -not -name "__init__.py" -delete

format:
	uv run autoflake --remove-all-unused-imports --ignore-init-module-imports --expand-star-imports --in-place --recursive .  --exclude=.venv 
	uv run black --exclude '.venv' .

lint:
	uv run flake8 . --exclude=.venv --ignore=E501,W503 --per-file-ignores="__init__.py:F401,F403" || true
	uv run black . --exclude=.venv