.PHONY: setup db run test lint fmt psql clean

PY ?= python
export PYTHONPATH := src

setup:            ## install dependencies
	$(PY) -m pip install -r requirements-dev.txt

db:               ## start PostgreSQL in Docker
	docker compose up -d db

run:              ## run the whole pipeline locally (needs `make db` or your own Postgres)
	$(PY) -m pipeline.run all --orders 5000

test:             ## run unit + integration tests (integration needs Postgres, see README)
	$(PY) -m pytest -q

lint:
	ruff check . && ruff format --check .

fmt:
	ruff format .

psql:             ## open a psql shell in the Docker database
	docker compose exec db psql -U pipeline -d retail

clean:
	docker compose down -v
	rm -f data/raw/*.csv output/*.csv
