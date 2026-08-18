.PHONY: install format lint type test test-integration run migrate compose-up compose-down seed

install:
	python -m pip install -e ".[dev]"

format:
	ruff format src tests migrations

lint:
	ruff check src tests migrations
	ruff format --check src tests migrations

type:
	mypy

test:
	pytest -m "not integration" --cov --cov-report=term-missing

test-integration:
	pytest -m integration --cov --cov-append --cov-report=term-missing

run:
	uvicorn opsdesk.main:app --reload --port 8000

migrate:
	alembic upgrade head

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

seed:
	opsdesk-seed
