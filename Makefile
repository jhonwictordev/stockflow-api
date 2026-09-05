.PHONY: install migrate run test test-postgres demo lint format typecheck audit quality seed docker-up docker-down

install:
	python -m pip install -r requirements-dev.txt

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --reload

test:
	pytest

test-postgres:
	pytest --database=postgres --evidence-dir=outputs/evidence

demo:
	python scripts/build_demo.py --evidence outputs/evidence/last-item-race.json

lint:
	ruff check .

format:
	ruff format .
	ruff check . --fix

typecheck:
	mypy app

audit:
	bandit -r app -x app/tests
	pip-audit -r requirements-dev.txt

quality: lint typecheck audit test

seed:
	python -m app.cli.seed_demo

docker-up:
	docker compose up --build

docker-down:
	docker compose down
