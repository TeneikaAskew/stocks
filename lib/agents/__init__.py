"""
Multi-agent AI Insights pipeline.

Pipeline topology (parallel analysts → debate → judge → trader →
risk debate → portfolio manager) orchestrated by lib.agents.orchestrator.
Deterministic SQL summarizers feed structured JSON into the analyst
tier so every LLM call reasons over real platform state rather than
hallucinated context.

Provider and model selection is per-role and runtime-configurable via
the `model_routing` Cloud SQL table; see lib.agents.model_routing and
the /admin dashboard in the platform frontend.
"""
