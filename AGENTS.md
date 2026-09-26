# Repository agent instructions

`CLAUDE.md` contains the complete project workflow and production rules. Read
and follow it before changing this repository. This file adds a tool-agnostic
architecture rule that applies to every automated contributor.

## Shared policy has one owner

Before implementing or changing cross-cutting behavior, search the active code
for existing implementations. Cross-cutting behavior includes time and market
sessions, configuration, parsing, provider access, retries, persistence,
serialization, coercion, notifications, and caching.

When the same domain policy exists in a second production location, stop and
assign it to a focused, tested module. Extend an existing focused owner when it
has the right contract. Otherwise create a narrowly named domain module after
confirming the duplication. Do not create generic `utils.py` or `helpers.py`
grab bags, and do not make scripts, routers, or orchestration entry points the
owner of reusable behavior.

For every cross-cutting change:

1. Inventory affected implementations and contracts before editing.
2. State the canonical owner and its input, output, error, timezone, and
   missing-data semantics.
3. Add contract tests at the owner and retain boundary integration tests.
4. Migrate all feasible callers in the same change. List any intentionally
   deferred callers and the compatibility/removal plan in the PR.
5. Delete superseded implementations; do not leave two optional sources of
   truth.

Prefer an existing **focused owner**, not merely an existing file. The
instruction to avoid unnecessary files must never be used to grow an unrelated
monolith.
