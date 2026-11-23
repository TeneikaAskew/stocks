# Implementation status and second-review decisions

The research produced runnable prototypes for both the morning workflow and the intraday monitor. The companion contains the consolidated implementation patch, before-images, candidate test sources and original test evidence. The included draft texts identify four existing Stocks feature lineages. Their status is draft. Reconcile them against the approved scope and production source on the publication date.

| Component | Local candidate | Outstanding release evidence |
|---|---|---|
| FEAT-PLAYBOOK-001 morning editions | Give internal, public and late briefs distinct editions. Persist the intended canonical update and retain immutable history and the exact premarket cutoff. | Production data-ready clock, natural update time, exact source and fallback/rollback readback. |
| FEAT-INSIGHT-001 handoff | Reserve three ticker-scoped workers after the internal edition commits. A delayed or retried worker reads the pinned edition and validates its reservation and source identity. | Actual queue and delivery receipt, retry effects and reconstruction from the real operational inputs. |
| FEAT-SIGNAL-001 intraday context | Apply the frozen opening-boundary update only after a valid unresolved pair and the first five completed minutes. Prototype paths for strength, checkpoint and original delivery grading have different scope from first-break research notices. | Scope and replay approval for the production release, durable notice identity, paired live decisions and transport acknowledgments. |
| FEAT-DEPLOY-001 schedule | Candidate clocks are 08:45 internal, 09:15 public and 09:25 refresh Eastern. Insights is triggered by committed internal data. | Reconcile the actual scheduler, job images, old timer deactivation, timing margin and rollback before any cutover. |

**Notification policy.** The research replay kept scanning after weak attempts, grouped repeated medium-or-better signals into uninterrupted episodes and observed level breaks separately. The November 17 harness preserved five native fires across its 70-minute integration window and suppressed the duplicate 10:40 callback in the same process. The separate full-day experiment counted nine first-direction notices that Tuesday. Restart-safe deduplication and production integration are open. Five native records on a date do not imply five successful Discord posts.

**Prior evidence.** The 09:35 holdout ran the monitor's opening observer against reconstructed issue-time inputs. The local integrated morning journey used PostgreSQL and simulated task and posting transports. A fake transport acknowledgment in that test establishes the local handoff behavior. Activate behavior changes only through their corresponding implementation and release gates.

**API and dashboard.** The separate Stocks readback and Solyra dashboard binding proposals, tests, patch bytes and checksums accompany the review. They cover how the new fields would reach the consumer. Each repository owns its implementation independently.
