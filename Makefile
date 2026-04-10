.PHONY: install install-unpinned lock test test-e2e test-scripts install-playwright pipeline pipeline-fast report sweep backtest clean help

PYTHON ?= python
TICKERS ?= IWM SPY QQQ

## Install dependencies (uses lock file for reproducibility)
install:
	$(PYTHON) -m pip install -r requirements.lock

## Install dependencies (unpinned, for upgrading)
install-unpinned:
	$(PYTHON) -m pip install -r requirements.txt

## Regenerate lock files from current environment
lock:
	pip freeze --exclude-editable | sort > requirements.lock
	@echo "Updated requirements.lock ($$(wc -l < requirements.lock) packages)"

## Run the full test suite (unit + integration, excludes E2E)
test:
	$(PYTHON) -m pytest tests/ -x -q --ignore=tests/test_e2e.py

## Run Playwright E2E tests for all web apps (requires: make install-playwright)
test-e2e:
	$(PYTHON) -m pytest tests/test_e2e.py -v

## Run script CLI regression tests only
test-scripts:
	$(PYTHON) -m pytest tests/test_scripts.py -v

## Install Playwright browsers and system deps (run once after pip install)
install-playwright:
	playwright install chromium
	playwright install-deps chromium

## Run full pipeline: backtest (base + strat) + sweep + report for all tickers
pipeline:
	$(PYTHON) scripts/run_pipeline.py --tickers $(TICKERS)

## Run pipeline without timeframe sweep (faster)
pipeline-fast:
	$(PYTHON) scripts/run_pipeline.py --tickers $(TICKERS) --skip-sweep

## Regenerate report from existing backtest CSVs
report:
	$(PYTHON) scripts/generate_backtest_report.py --tickers $(TICKERS)

## Run timeframe sweep for all tickers
sweep:
	@for t in $(TICKERS); do \
		$(PYTHON) scripts/run_timeframe_sweep.py --ticker $$t --use-strat || exit 1; \
	done

## Run backtest (base + strat) for a single ticker: make backtest TICKER=IWM
TICKER ?= IWM
backtest:
	$(PYTHON) scripts/run_backtest.py --ticker $(TICKER)
	$(PYTHON) scripts/run_backtest.py --ticker $(TICKER) --use-strat

## Remove generated backtest CSVs (keeps data/ structure)
clean:
	rm -f data/backtest_results/backtest_*.csv
	rm -f data/backtest_results/equity_*.csv
	rm -f data/backtest_results/timeframe_sweep_*.csv

## Show help
help:
	@echo "Available targets:"
	@echo "  make install             Install Python dependencies"
	@echo "  make install-playwright  Install Playwright browser binaries"
	@echo "  make test                Run unit/integration test suite"
	@echo "  make test-e2e            Run Playwright E2E tests for web apps"
	@echo "  make test-scripts        Run script CLI regression tests"
	@echo "  make pipeline            Full pipeline (backtest + sweep + report)"
	@echo "  make pipeline-fast       Pipeline without sweep"
	@echo "  make report              Regenerate report from existing CSVs"
	@echo "  make sweep               Run timeframe sweeps"
	@echo "  make backtest            Run backtest for TICKER (default: IWM)"
	@echo "  make clean               Remove generated CSV files"
