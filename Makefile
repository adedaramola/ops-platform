.PHONY: install format lint type test test-integration run migrate compose-up compose-down seed manifests backup-restore-test

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

manifests:
	kubectl kustomize deploy/kubernetes/base >/dev/null
	kubectl kustomize deploy/kubernetes/base/migration >/dev/null
	kubectl kustomize deploy/kubernetes/ai >/dev/null
	kubectl kustomize deploy/kubernetes/dockerhub >/dev/null
	kubectl kustomize deploy/kubernetes/dockerhub/migration >/dev/null
	kubectl kustomize deploy/kubernetes/dockerhub/ai >/dev/null

backup-restore-test:
	bash scripts/verify_backup_restore.sh
