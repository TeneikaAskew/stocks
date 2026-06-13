"""Magnitude Engine — research-only.

Predicts the magnitude bucket of the next bar's |close - open| move
in ATR-20 multiples. Companion to (not replacement for) strat_engine:
strat_engine predicts SHAPE (which extreme breaks); magnitude_engine
predicts DISTANCE (how far the bar travels).

NO PRODUCTION HOOKS. Walk-forward research only until the verdict
in docs/MAGNITUDE_ENGINE_RESULTS.md is "PASS" or "FAIL".
"""
