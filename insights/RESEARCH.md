# TradingAgents Research

**Source:** [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) · [trading-agents.ai](https://trading-agents.ai/) · arXiv 2412.20138
**Date:** 2026-04-15
**Purpose:** Evaluate the TradingAgents multi-agent framework for applicability to this trading dashboard's AI Insights tab. Decide what to copy, skip, and adapt.

---

## 1. Architecture — Agents & Communication

TradingAgents is a **graph with a debate stage**, not a pure pipeline. From `tradingagents/agents/`:

- **Analyst team** (run in parallel, configurable subset):
  - `market_analyst.py` — technicals via `stockstats` (MACD, RSI, Bollinger)
  - `fundamentals_analyst.py`
  - `news_analyst.py`
  - `social_media_analyst.py` — Reddit/sentiment
- **Researcher team**: `bull_researcher.py` and `bear_researcher.py` engage in **N rounds of structured debate** (`max_debate_rounds`, default 1).
- **Research manager** (`managers/research_manager.py`): judges the debate, produces an investment plan.
- **Trader** (`trader/trader.py`): turns the plan into a concrete trade proposal.
- **Risk management** (`risk_mgmt/`): three debators — `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py` — argue the trade for `max_risk_discuss_rounds` rounds.
- **Portfolio manager** (`managers/portfolio_manager.py`): final BUY / SELL / HOLD.

**Flow:** Analysts (parallel) → Bull/Bear debate loop → Research Manager → Trader → Risk debate (3-way) → Portfolio Manager.

## 2. Orchestration

**LangGraph**, fully custom graph. See `tradingagents/graph/`:

- `trading_graph.py` — top-level `TradingAgentsGraph` with `.propagate(ticker, date)`.
- `setup.py` — node/edge wiring.
- `conditional_logic.py` — controls debate loop continuation.
- `propagation.py` — state initialization.
- `signal_processing.py` — final BUY/SELL/HOLD extraction.
- `reflection.py` — post-trade reflection writing to a memory store.

State is a single typed dict (`agents/utils/agent_states.py`) carrying analyst reports, debate history, plans, and the final decision. **Memory** (`agents/utils/memory.py`) is a long-term FAISS-style store of past reflections, retrieved by similarity at run start.

## 3. LLM Calls & Caching

- Two-tier model split in `default_config.py`: `deep_think_llm` (default `gpt-5.4`) for managers/researchers, `quick_think_llm` (default `gpt-5.4-mini`) for analysts and tool-calling.
- Providers: OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, Zhipu, OpenRouter, Ollama, Azure, Bedrock (`llm_clients/factory.py`, `model_catalog.py`).
- **Per run, rough count** (defaults, all 4 analysts, 1 debate round, 1 risk round): ~4 analyst calls (each looping a few tool-calls) + 2 (bull/bear) + 1 research manager + 1 trader + 3 (risk) + 1 portfolio manager ≈ **15–25 LLM calls**. With `max_debate_rounds=2` and tool retries, 30–50.
- **Caching**: data-layer only — `data_cache_dir` for raw API pulls. **No prompt/response caching.** Does not use Anthropic prompt caching despite supporting Claude.

## 4. Output Shape

The `.propagate()` return is a string decision (BUY/SELL/HOLD) extracted by `signal_processing.py`. The full run also writes per-stage **markdown reports** (analyst sections, debate transcripts, trader plan, risk transcript, final decision) to `results_dir`.

**No structured entry/stop/target JSON** — the trader's plan is freeform text. To use this in a production UI, you must wrap it with your own JSON schema.

## 5. Data Sources

`tradingagents/dataflows/`:

- **Yahoo Finance** (`y_finance.py`, `yfinance_news.py`)
- **Alpha Vantage** (`alpha_vantage_*.py` — stock, fundamentals, indicators, news)

That's it — no Finnhub, no Polygon, no Tradier, **no options chains**. Indicators come from `stockstats`. Reddit sentiment exists in earlier versions.

## 6. Runtime / Cost

Neither the README nor `default_config.py` state numbers. Community reports put a **single-ticker run at ~$0.50–$3 with GPT-4-class models and 2–10 minutes** depending on debate rounds and analyst count. The arXiv paper reports backtest performance, not per-run cost. Treat these as folklore, not vendor-published.

## 7. License

**Apache 2.0** — commercial use OK with attribution and NOTICE preservation. Patent grant included. Safe to fork/embed.

## 8. Critical Evaluation

### What's actually novel

- **Bull/bear debate + judge pattern.** Two adversarial agents argue, a third adjudicates. Measurably improves over single-agent CoT in the paper. This is the real idea.
- **Two-tier model routing** (deep vs quick) — a cheap, effective cost lever.
- **Reflection memory** (`agents/utils/memory.py`) — past trades retrieved by embedding similarity and injected into prompts. Underrated.
- **Risk team as a *second* debate** — three personas (aggressive/conservative/neutral) reduce sycophancy.

### What's just prompt chaining with extra steps

- The analyst layer is essentially "ask GPT to summarize Yahoo data with a persona prompt." This dashboard already has better data than they do.
- **No structured output contracts.** Final decision is regex-extracted from prose. Fragile.
- No backtest of the agent system itself against simple baselines in production code — paper claims, repo doesn't verify.
- **No prompt caching** despite obvious repetition between runs.
- Tool-calling is `stockstats` wrappers around `yfinance`. Trivially replaceable.

### What to copy

1. **Bull/bear debate + judge** as a self-contained module. This is the highest-leverage import.
2. **Two-tier model routing** (cheaper tier for analysts, richer tier for managers/judges).
3. **Reflection memory backed by `journal_entries` + pgvector.** Near-free win since this codebase already has the table.
4. **Three-persona risk debate** before surfacing a trade idea.

### What to skip

1. **Their analyst layer wholesale.** Replace with **deterministic SQL summarizers** that emit structured JSON from this codebase's Cloud SQL (SPY/IWM/QQQ intraday + options + indicators). Their `yfinance` scrapes are strictly worse.
2. **LangGraph** — the graph here is 11 nodes; a hand-rolled async orchestrator is ~200 lines and easier to debug.
3. **Their freeform markdown output.** Define a Pydantic schema and force structured outputs at every agent boundary. Their lack of this is the biggest production weakness.
4. **Their data layer (`dataflows/`)** entirely.

### What to adapt

- Run the debate **per ticker-day** (daily precompute) and **per signal alert** in v2 (signal_alerts row is a natural trigger).
- Use **prompt caching on the system prompts and SQL-derived market context block** wherever the provider supports it (Anthropic cache_control, Gemini context caching when prompts exceed the minimum). Realistic savings on warm Anthropic cache: ~2× within the 5-minute TTL. Gemini needs ≥32k tokens; day-one benefit is nil.
- Replace `agents/utils/memory.py` with **pgvector on `journal_entries`**. Existing Cloud SQL Postgres + `vector` extension.

### Bottom line

The architectural ideas worth copying are **adversarial debate with a judge**, **two-tier routing**, and **reflection memory**. Everything else — the data layer, the orchestration framework, the analyst prompts, the unstructured outputs — is either inferior to what this codebase already has or actively a liability in production.

Plan on writing a thin orchestrator that wraps this codebase's existing SQL/insights stack with a debate-and-judge loop, forced structured outputs, and provider-agnostic LLM routing driven by a runtime admin dashboard.

## 9. Key File References in the Upstream Repo

- `tradingagents/graph/trading_graph.py` — entry point
- `tradingagents/graph/setup.py` — graph wiring
- `tradingagents/graph/conditional_logic.py` — debate loop control
- `tradingagents/agents/researchers/{bull,bear}_researcher.py` — debate prompts (worth reading)
- `tradingagents/agents/managers/research_manager.py` — the judge prompt
- `tradingagents/agents/risk_mgmt/{aggressive,conservative,neutral}_debator.py` — risk personas
- `tradingagents/agents/utils/memory.py` — reflection store
- `tradingagents/default_config.py` — knobs and defaults
