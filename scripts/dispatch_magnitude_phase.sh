#!/usr/bin/env bash
# Dispatch one magnitude_engine plan via Cloud Run Job task-parallel execution.
#
# The job spreads N cells across N parallel worker instances. Wall-clock
# is the slowest single cell (~30-60 min), not the sum.
#
# Per Phase-3 post-mortem (2026-05-28), every walk-forward dispatch should
# be followed by bootstrap gate-fragility (gate 5) and mechanism check
# (gate 6) on the resulting predictions. Use `--with-checks` flag to
# auto-dispatch those follow-ups against the just-completed run, OR run
# them manually with scripts/bootstrap_gate_fragility.py +
# scripts/check_event_window_concentration.py.
#
# Usage:
#   ./scripts/dispatch_magnitude_phase.sh no_backfill     # 27 cells (phases 0+1+3) parallel
#   ./scripts/dispatch_magnitude_phase.sh phase0          # 9 cells of phase0 parallel
#   ./scripts/dispatch_magnitude_phase.sh phase1          # 9 cells of phase1
#   ./scripts/dispatch_magnitude_phase.sh phase3          # 9 cells of phase3
#   ./scripts/dispatch_magnitude_phase.sh phase2          # 9 cells of phase2  (needs backfill!)
#   ./scripts/dispatch_magnitude_phase.sh phase4          # 9 cells of phase4  (needs backfill!)
#   ./scripts/dispatch_magnitude_phase.sh phase_calendar  # 9 cells of phase_calendar
#   ./scripts/dispatch_magnitude_phase.sh audit           # leakage audit (IWM 15m), single task
#
# Label-definition experiments (#1025). Both controls are OPTIONAL and default
# to the serving contract, body labels at MAGNITUDE_THRESHOLDS. Without them
# this script could dispatch only body runs, so the two experiments the
# research namespace exists for had no supported entrypoint:
#   ./scripts/dispatch_magnitude_phase.sh phase0 --label-mode=excursion
#   ./scripts/dispatch_magnitude_phase.sh phase0 --thresholds=0.35,0.75,1.25
#   ./scripts/dispatch_magnitude_phase.sh phase0 --label-mode=put --thresholds=0.35,0.75,1.25
# A non-default contract writes under research/magnitude_engine/_research/
# <slug>/ and is refused promotion by serving_contract_reason(), so it cannot
# reach LATEST. Read its artifacts with the analysis scripts' --research flag.
#
# The job must already exist:  ./gcp/deploy.sh magnitude-engine
# (Run from repo root after the :research image is built.)

set -euo pipefail
REGION=us-east1
JOB=magnitude-engine

plan="${1:-no_backfill}"
shift || true

# Optional label controls, forwarded to the execution. MAG_THRESHOLDS travels
# as an env override because the dataset builder reads it; --label-mode is a
# CLI flag on the module, so it travels in --args.
label_mode=""
thresholds=""
for arg in "$@"; do
  case "$arg" in
    --label-mode=*) label_mode="${arg#*=}" ;;
    --thresholds=*) thresholds="${arg#*=}" ;;
    --with-checks)
       # Documented in the header since the Phase-3 post-mortem but never
       # implemented: before this parser existed, extra arguments were simply
       # ignored and the phase still dispatched. Rejecting it here would turn
       # a silently-ignored flag into a dispatch that does nothing at all, so
       # it keeps dispatching and says what it is not doing.
       echo "NOTE: --with-checks is not implemented (it never was; the flag" >&2
       echo "      was ignored before this parser existed). Dispatching the" >&2
       echo "      phase, then run gates 5 and 6 yourself against the run id:" >&2
       echo "        python -m scripts.bootstrap_gate_fragility --run-id <exec> ..." >&2
       echo "        python -m scripts.check_event_window_concentration --run-id <exec> ..." >&2
       ;;
    *) echo "Unknown option: $arg" >&2
       echo "Valid: --label-mode=body|excursion|call|put  --thresholds=t0,t1,t2" >&2
       echo "       --with-checks (accepted, not implemented)" >&2
       exit 64 ;;
  esac
done

mag_args="-m,gcp.research.magnitude_engine.mag_walk_forward"
[ -n "$label_mode" ] && mag_args="${mag_args},--label-mode=${label_mode}"

# MAG_THRESHOLDS is itself comma-separated and gcloud splits --update-env-vars
# on commas, so "MAG_PLAN=phase0,MAG_THRESHOLDS=0.35,0.75,1.25" would set
# MAG_THRESHOLDS=0.35 and choke on the rest — a silently wrong label
# definition, which is the failure this whole change exists to prevent. The
# ^|^ custom-delimiter form is the documented escape (CLAUDE.md 3.5).
# ALWAYS name MAG_THRESHOLDS, empty when this dispatch is canonical.
# `gcloud run jobs execute --update-env-vars` MERGES: variables the override
# does not name keep their job-level value. A job still carrying a
# MAG_THRESHOLDS from an earlier experiment would therefore hand custom cut
# points to a dispatch that believes it is canonical, and the run would be
# written under _research/, kept out of the canonical SQL and refused
# promotion — the recalibration silently not performed. An empty value reads
# as absent in resolve_magnitude_thresholds(), so this clears it.
env_flag="--update-env-vars=^|^MAG_PLAN=${plan}|MAG_THRESHOLDS=${thresholds}"
if [ -n "$label_mode" ] || [ -n "$thresholds" ]; then
  echo "  label contract: label_mode=${label_mode:-body} thresholds=${thresholds:-default}"
  echo "  (non-default labels write under _research/<slug>/ and cannot be promoted)"
fi

case "$plan" in
  audit)
    echo "Dispatching leakage audit (IWM 15m, single task)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        --update-env-vars="MAG_PLAN=" \
        --args="-m,gcp.research.magnitude_engine.mag_leakage_audit,--ticker=IWM,--tf=15m" \
        --tasks=1 \
        --wait
    ;;
  no_backfill)
    echo "Dispatching plan=no_backfill (27 cells = 3 phases × 9, parallel)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        "$env_flag" \
        --args="${mag_args}" \
        --tasks=27 \
        --async
    ;;
  phase0|phase1|phase2|phase3|phase4|phase_calendar)
    echo "Dispatching plan=$plan (9 cells parallel)…"
    gcloud run jobs execute "$JOB" --region="$REGION" \
        "$env_flag" \
        --args="${mag_args}" \
        --tasks=9 \
        --async
    ;;
  *)
    echo "Unknown plan: $plan"
    echo "Valid: no_backfill | phase0 | phase1 | phase2 | phase3 | phase4 | audit"
    exit 1
    ;;
esac
