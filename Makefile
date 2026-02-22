.PHONY: install test pipeline pipeline-fast report sweep backtest clean

PYTHON ?= python
TICKERS ?= IWM SPY QQQ

## Install dependencies
install:
	$(PYTHON) -m pip install -r requirements.txt

## Run the full test suite
test:
	$(PYTHON) -m pytest tests/ -x -q

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
		$(PYTHON) scripts/run_timeframe_sweep.py --ticker $$t --use-strat; \
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
	@echo "  make install        Install Python dependencies"
	@echo "  make test           Run test suite"
	@echo "  make pipeline       Full pipeline (backtest + sweep + report)"
	@echo "  make pipeline-fast  Pipeline without sweep"
	@echo "  make report         Regenerate report from existing CSVs"
	@echo "  make sweep          Run timeframe sweeps"
	@echo "  make backtest       Run backtest for TICKER (default: IWM)"
	@echo "  make clean          Remove generated CSV files"
