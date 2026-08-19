run:
	uv run uvicorn documenter.app:app --reload --port 8000

start:
	uv run python -m documenter.run

test:
	uv run pytest -q

.PHONY: run start test
