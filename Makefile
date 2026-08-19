run:
	uv run uvicorn documenter.app:app --reload --port 8000

test:
	uv run pytest -q

.PHONY: run test
