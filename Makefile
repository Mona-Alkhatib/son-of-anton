.PHONY: install lint typecheck test test-integration db-up db-migrate demo

install:
	uv sync --all-extras

lint:
	uv run ruff check anton tests
	uv run ruff format --check anton tests

typecheck:
	uv run mypy anton

test:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v -m integration

db-up:
	docker compose up -d postgres --wait

db-migrate: db-up
	dbmate --url "$$DATABASE_URL" --migrations-dir migrations up
