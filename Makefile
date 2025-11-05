PYTHON ?= python3
VENV ?= .venv
BIN_DIR := $(VENV)/bin
PYTHON_BIN := $(BIN_DIR)/python
PIP := $(PYTHON_BIN) -m pip

HOST ?= 127.0.0.1
PORT ?= 8001

START_ARGS :=
ifneq ($(SKIP_UPDATE),)
START_ARGS += --skip-update
endif

.PHONY: install install-dev update start changelog test clean

install:
	@if [ ! -f "$(PYTHON_BIN)" ]; then \
		$(PYTHON) -m venv $(VENV); \
	fi
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

install-dev: install
	@$(PIP) install -r requirements-dev.txt

update: install
	@$(PYTHON_BIN) scripts/update_models.py

start: install
	@$(PYTHON_BIN) scripts/start_local.py --host $(HOST) --port $(PORT) $(START_ARGS)

changelog: install
	@$(PYTHON_BIN) scripts/build_changelog.py

test: install-dev
	@$(PYTHON_BIN) -m pytest

clean:
	rm -rf $(VENV)
