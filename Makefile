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

.PHONY: install install-dev update test-update-snapshots start changelog release test clean

install:
	@if [ ! -f "$(PYTHON_BIN)" ]; then \
		$(PYTHON) -m venv $(VENV); \
	fi
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

install-dev: install
	@$(PIP) install -r requirements-dev.txt

update:
	@$(PYTHON_BIN) scripts/update_models.py

test-update-snapshots:
	@$(PYTHON_BIN) scripts/update_provider_snapshots.py

start:
	@$(PYTHON_BIN) scripts/start_local.py --host $(HOST) --port $(PORT) $(START_ARGS)

changelog:
	@$(PYTHON_BIN) scripts/build_changelog.py

release: update
	@$(PYTHON_BIN) scripts/publish_release.py

test:
	@$(PYTHON_BIN) -m pytest

clean:
	rm -rf $(VENV)
