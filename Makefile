.PHONY: install migrate run test lint format typecheck audit quality seed docker-up docker-down

install:
	python -m pip install -r requirements-dev.txt

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --reload

test:
	pytest

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
