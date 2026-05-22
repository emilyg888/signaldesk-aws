PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: install test synth deploy destroy

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r infrastructure/requirements.txt

test:
	$(PY) -m pytest tests

synth:
	cd infrastructure && ../$(PY) -m aws_cdk synth

deploy:
	bash scripts/deploy.sh

destroy:
	bash scripts/destroy.sh
