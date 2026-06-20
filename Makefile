.PHONY: eval test clean

eval:
	python evals.py

test:
	pytest

clean:
	rm -rf __pycache__ .pytest_cache
