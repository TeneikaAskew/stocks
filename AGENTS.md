## Delivery gate
Read `.claude/skills/product-delivery/SKILL.md` and follow it for any code change. The same gate
(`scripts/gate/spec_gate.py`) runs on every commit and every PR regardless of which agent authored it.
A branch that changes code must carry the FEAT-ID: `feature/<feat-id>-<slug>` or `fix/<feat-id>-<slug>`.
The only other shapes are `docs/<slug>` (documentation only), `chore/<slug>` (dependency fields of manifests,
lockfiles and the gate's own files), `spike/<slug>` (local commits, never a PR) and `bot/superpowers-*`
(the vendored skills), as Phase 0 of the product-delivery skill sets out.
