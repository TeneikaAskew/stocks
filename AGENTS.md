## Delivery gate
Read `.claude/skills/product-delivery/SKILL.md` and follow it for any code change. The same gate
(`scripts/gate/spec_gate.py`) runs on every commit and every PR regardless of which agent authored it.
Branch names must carry the FEAT-ID: `feature/<feat-id>-<slug>` or `fix/<feat-id>-<slug>`.
