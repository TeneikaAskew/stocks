#!/usr/bin/env python3
"""Refresh Architecture.drawio from the live GCP snapshot.

The diagram is the visual companion of ARCHITECTURE.md and had not been
regenerated since 2026-05-22 (49 crons, 42 jobs, a React SPA on the API
service, GitHub Pages and Apps Script surfaces that no longer exist). This
script makes the refresh repeatable:

* rewrites the title, subtitle and group headers with live counts;
* renames or retires surfaces and jobs that changed (replacement table);
* deletes cells (and their edges) for retired surfaces;
* adds the staging API service and the Cloud Build deploy path;
* regenerates the "jobs not shown above" grid from every live job that the
  hand-placed fetcher / compute / on-demand rows do not already carry;
* applies the same label replacements to Architecture-icons.drawio where the
  identical label exists.

Usage:
    python -m scripts.maintenance.refresh_architecture_drawio --snapshot live.json [--check]

--check parses, verifies every live job name appears as a label on the main
page and no retired label remains, and exits non-zero on a miss.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

REPO = pathlib.Path(__file__).resolve().parents[2]
MAIN = REPO / "Architecture.drawio"
ICONS = REPO / "Architecture-icons.drawio"

# Exact-substring replacements applied to every cell label on every page.
REPLACEMENTS: list[tuple[str, str]] = [
    ("solyra-api-prod\nCloud Run Service\nFastAPI API (IAP)",
     "solyra-api-staging / -prod\nCloud Run Services\nFastAPI only; the browser reaches staging (Firebase), prod is IAP"),
    ("Browser\n(internal team React UI)", "solyra React UI\n(Lovable-published, separate repo)"),
    ("Browser\nReact dashboard", "solyra React UI\n(separate repo)"),
    ("React dashboard", "solyra React UI"),
    ("Anthropic API / Vertex AI\nLLM (insights, agents)", "Vertex AI\nGemini 3.1 Flash Lite (insights, brief) + text-embedding-005"),
    ("FastAPI + React (mounts 13 routers:\ninsights, live, options, playbook,\nbacktest, signals, journal, dashboard,\ncatalysts, admin, analytics, config, health)",
     "FastAPI API only — no SPA since #957 (20 routers:\nlive, grid, options, playbook, backtest, signals,\ninsights, journal, dashboard, catalysts, admin,\nanalytics, config, health, glossary, magnitude,\nearnings, waitlist, preferences, profile)"),
    ("▸ prod domain: stocks.insightscollective.org (IAP + managed TLS)\n▸ deploy: staging revision → promote workflow",
     "▸ IAP-gated, AUTH_MODE=iap, SA trading-platform-svc@\n▸ deploy: deploy-solyra-api-prod Cloud Build trigger (manual digest promote)"),
    ("Cloud Run Service\nFastAPI + React", "Cloud Run Service\nFastAPI API (IAP)"),
    ("FastAPI + React", "FastAPI API"),
    ("GitHub Actions\n20 workflows: backups, audits, db-query,\nsheet downloads, platform deploy + promote",
     "GitHub Actions (5 workflows) + Cloud Build (3 triggers)\nCI, manual staging deploy, REST bridge,\nfailure handler, monthly doc refresh; API + schema deploys"),
    ("GitHub Actions\n20 workflows: backups, audits, db-query,\nsheet downloads, deploys, failure-handler",
     "GitHub Actions (5 workflows) + Cloud Build (3 triggers)\nCI, manual staging deploy, REST bridge,\nfailure handler, monthly doc refresh; API + schema deploys"),
    ("fetch-catalyst-calendar\nBenzinga catalysts", "fetch-av-options-realtime\nAV realtime options chain\nevery 5 min in RTH → etf_options_snapshots"),
    ("fetch-av-options-backfill\none-shot historical options\n(SPY/IWM/QQQ/SPX from 2016)", "fetch-av-options-backfill\nnightly 21:00 ET + monthly\nAV HISTORICAL_OPTIONS → etf_options_snapshots"),
    ("fetch-av-earnings-options-backfill ★\nEW options chains historical\n(on-demand)", "earnings-options-backfill\nEW-window options chains\n(on-demand)"),
    ("migrate-to-gcp\none-shot parquet→GCS+SQL", "db-query\nscripts/db_query_cr.sh dispatch\n(443-only sandboxes)"),
    ("backtest\n/backtest slash cmd\n(2 GiB)", "backtest\n/backtest slash cmd\n(2 GiB / 15 min)"),
    ("db-query.yml\nCloud SQL bridge for sandboxed\nClaude Code on the web", "deploy-staging.yml\nmanual WIF redeploy of\nsolyra-api-staging (+ schema apply)"),
    ("Backup mirrors\nfetch-market-data, earnings-options-analytics, etc.", "backtest-pipeline.yml\nCI tests on push / PR\n+ nightly canary on main"),
    ("Heavy backtests\nwalk-forward audits\nfreshness audits", "gh-api.yml\nGitHub REST bridge for\nfenced sandboxes"),
    ("download-google-sheets.yml\nsheet → Cloud SQL ingest", "Cloud Build: deploy-solyra-api-staging\npush to main → build by digest\n→ solyra-api-staging"),
    ("deploy-trading-apps.yml\nchart-viewer → GitHub Pages\n(options-heatseeker retired #255)", "Cloud Build: deploy-solyra-api-prod\nmanual: promote the digest\nstaging serves → solyra-api-prod"),
    ("deploy-trading-apps.yml\nchart-viewer → GitHub Pages\n(options-heatseeker archived 2026-05-04)", "Cloud Build: deploy-solyra-api-prod\nmanual: promote the digest\nstaging serves → solyra-api-prod"),
    ("Audit / type-check / test workflows\nsecurity-review, audit-review,\nvalidate-data, pre-deploy-check", "Cloud Build: apply-schema-on-change\npush touching gcp/schema.sql\n→ apply-schema-migrations job"),
    ("refresh-architecture-docs.yml (monthly Gemini regen)", "refresh-architecture-docs.yml (monthly: live snapshot → rendered blocks → gated prose update)"),
    ("⑩ GitHub Actions — 14 active workflows: backups, audits, sandbox bridges, deploys", "⑩ GitHub Actions (5 workflows) and Cloud Build (3 triggers) — CI, deploys, bridges, doc refresh"),
    ("⑦ Cloud Run Services (always-on)", "⑦ Cloud Run Services (4; discord-interactions min-instances 1, others 0)"),
    ("7:15 ET — earnings-calendar refreshes today's reporters", "19:00 ET prior evening — daily-earnings-refresh-calendar / -history / -reactions"),
    ("4️⃣  8:20 ET — premarket-refresh polls AV intraday → gap_pct, pre_high/low/vwap\n5️⃣  8:30 ET — premarket-brief reads everything → Discord (multi-embed)",
     "4️⃣  8:20 ET — premarket-refresh polls AV intraday → gap_pct, pre_high/low/vwap\n5️⃣  8:30 ET — premarket-brief → Discord; 8:35 earnings-reactions-brief; 8:10 auto-refresh-top-n pre-warmed insights"),
    ("Browser → solyra-api-prod Cloud Run Service", "solyra UI → solyra-api-staging (Firebase) or solyra-api-prod (IAP)"),
    ("User-triggered single-ticker refresh from React dashboard", "User-triggered single-ticker refresh from the solyra UI"),
    ("Insulates the React dashboard", "Insulates the UI"),
    ("daily 7:15 ET", "daily 19:00 ET (prior evening)"),
    ("7:15 ET", "19:00 ET (prior evening)"),
    ("Cloud Scheduler (49 crons)", "Cloud Scheduler (65 live entries)"),
    ("Cloud Scheduler (66 live entries)", "Cloud Scheduler (65 live entries)"),
    ("trading-runner SA\nruntime identity for all Jobs", "trading-runner@ (jobs, Discord, notifier)\ntrading-platform-svc@ (API services)"),
]

# Cells retired outright (their edges go too).
DELETE_IDS = {"ext_ghpages", "ext_gas", "svc_sm_orphan"}

# New cells on the main page: (id, value, style, x, y, w, h)
NEW_CELLS = [
    ("svc_st",
     "solyra-api-staging\nFastAPI API — PUBLIC edge, Firebase login (AUTH_MODE=firebase)\n"
     "▸ open self-signup over production data (#943)\n"
     "▸ api.stocks.insightscollective.org → this service (since 2026-09-06;\n"
     "   the apex stocks.insightscollective.org is reserved for the SPA and Firebase auth emails, #1006)\n"
     "▸ deploy: deploy-solyra-api-staging trigger on push to main",
     "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#b85450;fontSize=10;fontStyle=1;",
     2000, 675, 220, 95),
]

SUBTITLE_ID = "subtitle"
SCHED_GROUP_ID = "sched_group"
GHA_GROUP_ID = "gha_group"
SCHED_LABELS = {
    "sched_label1": "Post-close: 21:00 av-options-daily / av-intraday-nightly • 21:15 playbook-resolver • 22:00 options-daily-features • 22:30 gamma-levels • 23:00 fetch-market-data + evaluate-ew-strikes • 23:15 options-daily-greeks • 23:35 strat-engine",
    "sched_label2": "Pre-market: 06:30 fred-rates • 07:00 economic-events, insider-transactions, sec-filings-intraday • 07:30 refresh-earnings-views • 08:10 auto-refresh-top-n • 08:20 premarket-refresh • 08:30 premarket-brief • 08:35 earnings-reactions-brief • 08:45 insight-pipeline",
    "sched_label3": "Intraday: 09:15 insight-discord-push • 09:25 signal-monitor + magnitude-inference • 09:45/10:00 ORB • every 5 min av-options-realtime • hourly news-sentiment/-topics, top-movers-intraday, freshness-watchdog • 16:30 eod-resolver • 17:00 realtime-gex • 19:00–19:30 earnings trio",
}
ADDON_GROUP_ID = "addon_group"
ADDON_PREFIX = "addon_"
GRID_COLS, GRID_W, GRID_H, GRID_GAP = 9, 240, 62, 12
GRID_X0, GRID_Y0 = 60, 1540


def _cells(page: ET.Element) -> list[ET.Element]:
    return page.find("mxGraphModel/root").findall("mxCell")


def _job_labels(page: ET.Element) -> set[str]:
    names = set()
    for c in _cells(page):
        v = c.get("value") or ""
        first = re.sub(r"<[^>]+>", "", v).split("\n")[0].strip()
        first = first.replace("★", "").strip()
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", first):
            names.add(first)
    return names


def apply_replacements(root: ET.Element) -> int:
    n = 0
    for c in root.iter("mxCell"):
        v = c.get("value")
        if not v:
            continue
        new = v
        for old, rep in REPLACEMENTS:
            if old in new:
                new = new.replace(old, rep)
        if new != v:
            c.set("value", new)
            n += 1
    return n


def refresh_main(root: ET.Element, live: dict) -> None:
    page = root.findall("diagram")[0]
    parent = page.find("mxGraphModel/root")
    cells = _cells(page)
    by_id = {c.get("id"): c for c in cells}
    counts = live["counts"]
    jobs = sorted(live["jobs"])
    read = live["read_at"][:10]

    by_id["title"].set("value", "Stocks Trading Platform — GCP Architecture (project: adept-mountain-474619-d4, us-east1)")
    by_id[SUBTITLE_ID].set("value",
        f"{counts['jobs']} Cloud Run Jobs (live) • {counts['services']} Cloud Run Services • {counts['schedulers']} Cloud Scheduler entries "
        f"• Cloud SQL trading-db: {len(live.get('db_tables', {}))} relations • {counts['secrets']} secrets • read live {read} — companion to ARCHITECTURE.md")
    paused = [n for n, x in live["schedulers"].items() if x.get("state") != "ENABLED"]
    paused_note = f"; {len(paused)} paused: {', '.join(paused)}" if paused else "; none paused"
    wf = live.get("_workflows")
    gha_label = (f"⑩ GitHub Actions ({len(wf)} workflows) and Cloud Build ({len(live.get('cloudbuild_triggers', []))} triggers) — CI, deploys, bridges, docs-vs-live check, doc refresh"
                 if wf is not None else
                 f"⑩ GitHub Actions and Cloud Build ({len(live.get('cloudbuild_triggers', []))} triggers) — CI, deploys, bridges, docs-vs-live check, doc refresh")
    if GHA_GROUP_ID in by_id:
        by_id[GHA_GROUP_ID].set("value", gha_label)
    by_id[SCHED_GROUP_ID].set("value", f"② Cloud Scheduler — {counts['schedulers']} live entries, all America/New_York (read {read}{paused_note})")
    for cid, text in SCHED_LABELS.items():
        by_id[cid].set("value", text)

    # delete retired cells and any edge touching them
    for c in list(cells):
        if c.get("id") in DELETE_IDS or c.get("source") in DELETE_IDS or c.get("target") in DELETE_IDS:
            parent.remove(c)

    # add new cells
    for cid, value, style, x, y, w, h in NEW_CELLS:
        if cid in by_id:
            # the cell's text is owned by this table; geometry stays as drawn
            by_id[cid].set("value", value)
            continue
        cell = ET.SubElement(parent, "mxCell", id=cid, value=value, style=style, parent="1", vertex="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h), **{"as": "geometry"})

    # regenerate the add-on group as "jobs not shown above"
    cells = _cells(page)
    for c in list(cells):
        cid = c.get("id") or ""
        # Only cells this script generated. An earlier `or cid.endswith("_a")`
        # also removed the hand-authored flow_a and job_*_a detail cards
        # (Codex, PR #1009).
        if cid.startswith(ADDON_PREFIX) and cid != ADDON_GROUP_ID:
            parent.remove(c)
    shown = _job_labels(page)
    missing = [j for j in jobs if j not in shown]
    rows = math.ceil(len(missing) / GRID_COLS) if missing else 0
    group = by_id[ADDON_GROUP_ID]
    group.set("value", f"⓫ Cloud Run Jobs not drawn in ③–⑤ ({len(missing)}) — options analytics, research image, audits, ops. Live {read}; ★ = no deploy_* function in gcp/deploy.sh (hand-created)")
    geo = group.find("mxGeometry")
    geo.set("height", str(60 + rows * (GRID_H + GRID_GAP) + 130))
    repo_jobs = set(live.get("_repo_jobs", []))
    for i, name in enumerate(missing):
        j = live["jobs"][name]
        r, col = divmod(i, GRID_COLS)
        star = "" if (not repo_jobs or name in repo_jobs) else " ★"
        img = j["image"].split("/")[-1]
        tag = img.split(":")[1] if ":" in img else "latest"
        last = j["last_execution"]["time"][:10] or "never"
        text = f"{name}{star}\n{(j['command'] + ' ' + j['args']).strip()[:60]}\n{j['memory']}/{j['cpu']}cpu • {tag} • last {last}"
        fill = "#e1d5e7" if tag.startswith("research") else "#dae8fc"
        cell = ET.SubElement(parent, "mxCell", id=f"addon_job_{i}", value=text,
                             style=f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=#6c8ebf;fontSize=9;align=left;spacingLeft=6;",
                             parent="1", vertex="1")
        ET.SubElement(cell, "mxGeometry", x=str(GRID_X0 + col * (GRID_W + GRID_GAP)), y=str(GRID_Y0 + r * (GRID_H + GRID_GAP)),
                      width=str(GRID_W), height=str(GRID_H), **{"as": "geometry"})
    y_after = GRID_Y0 + rows * (GRID_H + GRID_GAP) + 10
    sql = live.get("sql", {})
    notes = [
        ("addon_schema_box",
         f"★ Cloud SQL: {sql.get('tier','')} • {sql.get('disk_gb','')} GB • public IPv4 {'on' if sql.get('ipv4_enabled') else 'off'} • PITR {'on' if sql.get('pitr') else 'off'} • "
         f"{len(live.get('db_tables', {}))} live relations (66 declared in gcp/schema.sql; strat_features_*, magnitude_*, gamma_levels_eod … created at runtime) • weekly pg_dump to gs://…/sql-dumps/",
         60, y_after, 2280, 40),
        ("addon_auth_box",
         "★ Auth: AUTH_MODE iap (solyra-api-prod) / firebase (solyra-api-staging) / open (local) • roles from user_roles (admin, user, dev) • /api/me → is_admin, is_dev • CORS Lovable hosts only outside iap",
         60, y_after + 50, 2280, 40),
        ("addon_note",
         f"📝 Refreshed {read} by scripts/maintenance/refresh_architecture_drawio.py from the live snapshot; ARCHITECTURE.md is the text of record.",
         60, y_after + 100, 2280, 30),
    ]
    for cid, text, x, y, w, h in notes:
        cell = ET.SubElement(parent, "mxCell", id=cid, value=text,
                             style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;align=left;spacingLeft=8;",
                             parent="1", vertex="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h), **{"as": "geometry"})
    # page height
    model = page.find("mxGraphModel")
    model.set("pageHeight", str(max(int(model.get("pageHeight", "1900")), y_after + 200)))


def check(root: ET.Element, live: dict) -> list[str]:
    page = root.findall("diagram")[0]
    labels = _job_labels(page)
    problems = [f"job not drawn: {j}" for j in sorted(live["jobs"]) if j not in labels]
    for c in root.iter("mxCell"):
        if c.get("id") == GHA_GROUP_ID and "14 active workflows" in (c.get("value") or ""):
            problems.append("gha_group still carries the 2026-05 '14 active workflows' label")
    # the hand-authored detail cards must survive regeneration (Codex, PR #1009)
    ids = {c.get("id") for c in root.iter("mxCell")}
    for hand in ("flow_a", "job_smer_a", "job_ppr_a", "job_erb_a", "job_bdi_a"):
        if hand not in ids:
            problems.append(f"hand-authored cell {hand} is missing")
    text = ET.tostring(root, encoding="unicode")
    for stale in ("GitHub Pages", "Google Apps Script", "download-google-sheets.yml", "fetch-catalyst-calendar",
                  "migrate-to-gcp", "FastAPI + React", "db-query.yml", "trading-platform-staging", "React dashboard", "~49"):
        if stale in text:
            problems.append(f"stale label still present: {stale}")
    return problems


def _write(tree: ET.ElementTree, path: pathlib.Path) -> None:
    tree.write(path, encoding="unicode", xml_declaration=False)
    path.write_text(path.read_text() + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--repo-jobs", help="JSON list of jobs declared in deploy.sh (marks hand-created jobs with ★)")
    ap.add_argument("--check", action="store_true", help="verify only; do not write")
    a = ap.parse_args(argv)
    live = json.loads(pathlib.Path(a.snapshot).read_text())
    if a.repo_jobs:
        live["_repo_jobs"] = json.loads(pathlib.Path(a.repo_jobs).read_text())
    tree = ET.parse(MAIN)
    root = tree.getroot()
    if not a.check:
        n = apply_replacements(root)
        refresh_main(root, live)
        _write(tree, MAIN)
        print(f"{MAIN.name}: {n} labels replaced, main page regenerated")
        if ICONS.exists():
            itree = ET.parse(ICONS)
            m = apply_replacements(itree.getroot())
            if m:
                _write(itree, ICONS)
            print(f"{ICONS.name}: {m} labels replaced")
        tree = ET.parse(MAIN)
        root = tree.getroot()
    problems = check(root, live)
    for p in problems:
        print(f"::error::{p}")
    print(f"drawio check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
