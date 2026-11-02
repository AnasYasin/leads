# Same command the GitHub workflow runs (.github/workflows/tests.yml). Run it before every push.
PY ?= /home/anas-yasin/miniconda3/envs/jobsearch/bin/python
RUFF ?= /home/anas-yasin/miniconda3/envs/aidj/bin/ruff

ci:
	$(RUFF) check scripts tests
	$(PY) -m pytest -q tests

.PHONY: ci
