.PHONY: install install-unpinned lock test test-e2e test-scripts install-playwright pipeline pipeline-fast report sweep backtest dev api web stop clean setup-notifier notifier help

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

## Start the full platform locally: FastAPI backend + Vite dev server in parallel.
## Logs are interleaved and prefixed [api]/[web]. Ctrl+C stops both cleanly.
## Sources ./.env automatically if it exists (for GOOGLE_APPLICATION_CREDENTIALS etc.)
dev:
	@bash scripts/dev_server.sh

## Start only the FastAPI backend (port 8000)
api:
	@bash -c 'set -a; [ -f ./.env ] && . ./.env; set +a; cd platform && exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload'

## Start only the Vite dev server (port 5173)
web:
	@cd platform && exec npm run dev

## Kill any running uvicorn / vite dev processes on ports 8000 and 5173.
## Uses the classic [x]yz regex trick so pkill doesn't match its own command line.
stop:
	@echo "Stopping platform dev servers..."
	-@pkill -f '[u]vicorn api.main:app' 2>/dev/null; true
	-@pkill -f '[v]ite.*platform' 2>/dev/null; true
	-@pkill -f '[n]ode.*platform/node_modules/.bin/vite' 2>/dev/null; true
	@sleep 1 2>/dev/null; echo "Done."

## One-time: store GitHub PAT + repo slug in GCP Secret Manager for the failure notifier.
## Auto-detects repo from git remote. PAT is resolved in order:
##   1. GH_PAT env var          (export GH_PAT=ghp_xxx && make setup-notifier)
##   2. gh CLI auth token       (if gh is installed and authenticated)
##   3. Interactive prompt       (fallback)
setup-notifier:
	./gcp/deploy.sh setup-notifier-secrets

## Build Docker image + deploy failure-notifier Cloud Run service, Pub/Sub topic,
## push subscription (with dead-letter), and Cloud Logging sink.
## Requires: make setup-notifier (one-time) and gcloud auth login.
notifier:
	./gcp/deploy.sh notifier

## Remove generated backtest CSVs (keeps data/ structure)
clean:
	rm -f data/backtest_results/backtest_*.csv
	rm -f data/backtest_results/equity_*.csv
	rm -f data/backtest_results/timeframe_sweep_*.csv

## Show help
help:
	@echo "Platform dev:"
	@echo "  make dev                 Start FastAPI (port 8000) + Vite (port 5173) together"
	@echo "  make api                 Start only the FastAPI backend"
	@echo "  make web                 Start only the Vite dev server"
	@echo "  make stop                Kill any running dev servers"
	@echo ""
	@echo "Pipeline & backtests:"
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
	@echo ""
	@echo "GCP deployment:"
	@echo "  make setup-notifier      One-time: store GitHub PAT + repo in Secret Manager"
	@echo "  make notifier            Build + deploy failure-notifier service + log sink"
