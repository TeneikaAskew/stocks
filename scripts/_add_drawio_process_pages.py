"""Append five per-process detail pages to Architecture.drawio.

Page 1 is the high-level swimlane overview. Pages 2-6 each tell ONE
story end-to-end with numbered arrow labels:

  Page 2 — 🌙 Daily Nightly Write Path
  Page 3 — 🌅 Daily Morning Read Path
  Page 4 — ⚡ On-Demand AI Insight Refresh
  Page 5 — 🚨 Failure Pipeline
  Page 6 — 💬 Discord Slash-Command Path
  Page 7 — 🎯 Earnings Pipeline

Each page is self-contained — its own boxes, arrows, and numbered
steps — so no cross-page references. Color vocabulary matches Page 1.

Re-runnable: strips pages 2+ (everything after the first <diagram>) then
appends fresh.

Run:  py scripts/_add_drawio_process_pages.py
"""

from __future__ import annotations
import re
import uuid
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "Architecture.drawio"

# Color palette (must match Page 1)
PALETTE = {
    "ext":     ("#d5e8d4", "#82b366"),  # external apis / Discord / browser
    "sched":   ("#fff2cc", "#d6b656"),  # Cloud Scheduler + GitHub Actions
    "fetch":   ("#dae8fc", "#6c8ebf"),  # Cloud Run Jobs - Fetchers
    "comp":    ("#d4e1f5", "#4d7eb8"),  # Cloud Run Jobs - Compute
    "ond":     ("#b1ddf0", "#10739e"),  # Cloud Run Jobs - On-Demand
    "svc":     ("#b0e3e6", "#0e8088"),  # Cloud Run Services
    "lib":     ("#e1d5e7", "#9673a6"),  # Shared lib/
    "data":    ("#fad7ac", "#b46504"),  # Cloud SQL / GCS / Secrets
    "async":   ("#e6d5e7", "#9673a6"),  # Cloud Tasks / Pub/Sub / Logging
    "warn":    ("#f8cecc", "#b85450"),  # Failure / orphan
    "white":   ("#ffffff", "#666666"),  # plain box
}

EDGE_COMMON = (
    "endArrow=classic;html=1;edgeStyle=orthogonalEdgeStyle;rounded=1;"
    "jettySize=auto;orthogonalLoop=1;"
)


def vertex(cid: str, value: str, x: int, y: int, w: int, h: int,
           color: str = "white", *, bold: bool = False, dashed: bool = False) -> str:
    fill, stroke = PALETTE[color]
    style_extras = ""
    if bold:
        style_extras += "fontStyle=1;"
    if dashed:
        style_extras += "dashed=1;"
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"fontSize=11;{style_extras}"
    )
    return (
        f'                <mxCell id="{cid}" value="{value}" style="{style}" '
        f'vertex="1" parent="1">\n'
        f'                    <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
        f'as="geometry"/>\n'
        f'                </mxCell>'
    )


def text(cid: str, value: str, x: int, y: int, w: int, h: int,
         *, size: int = 16, bold: bool = True, italic: bool = False) -> str:
    fs = "fontStyle=" + ("1" if bold else "0") + (";fontStyle=2" if italic else "")
    style = (
        f"text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
        f"whiteSpace=wrap;rounded=0;fontSize={size};{fs};"
    )
    if italic:
        style = style.replace("fontStyle=1", "fontStyle=2")
    return (
        f'                <mxCell id="{cid}" value="{value}" style="{style}" '
        f'vertex="1" parent="1">\n'
        f'                    <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
        f'as="geometry"/>\n'
        f'                </mxCell>'
    )


def edge(cid: str, src: str, tgt: str, label: str = "", *,
         color: str = "#444444", dashed: bool = False, width: int = 2,
         exit_side: str = "auto", entry_side: str = "auto",
         start_arrow: bool = False) -> str:
    """exit_side / entry_side: one of 'top','bottom','left','right','auto'."""
    sides = {
        "top":    (0.5, 0),
        "bottom": (0.5, 1),
        "left":   (0, 0.5),
        "right":  (1, 0.5),
    }
    anchors = ""
    if exit_side in sides:
        ex, ey = sides[exit_side]
        anchors += f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;"
    if entry_side in sides:
        nx, ny = sides[entry_side]
        anchors += f"entryX={nx};entryY={ny};entryDx=0;entryDy=0;"
    style = anchors + EDGE_COMMON + f"strokeColor={color};strokeWidth={width};"
    if dashed:
        style += "dashed=1;"
    if start_arrow:
        style += "startArrow=classic;startFill=1;"
    return (
        f'                <mxCell id="{cid}" value="{label}" style="{style}" '
        f'edge="1" parent="1" source="{src}" target="{tgt}">\n'
        f'                    <mxGeometry relative="1" as="geometry"/>\n'
        f'                </mxCell>'
    )


def page(name: str, width: int, height: int, cells: list[str]) -> str:
    pid = uuid.uuid4().hex[:20]
    body = "\n".join(cells)
    return (
        f'    <diagram name="{name}" id="{pid}">\n'
        f'        <mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">\n'
        f'            <root>\n'
        f'                <mxCell id="0"/>\n'
        f'                <mxCell id="1" parent="0"/>\n'
        f'{body}\n'
        f'            </root>\n'
        f'        </mxGraphModel>\n'
        f'    </diagram>'
    )


# =============== PAGE 2 — 🌙 Nightly Write ===============
def page_nightly_write() -> str:
    cells = []
    cells.append(text("p2_title",
        "🌙 Daily Nightly Write Path — post-close 11pm ET",
        40, 30, 1300, 32, size=20))
    cells.append(text("p2_sub",
        "fetch-market-data + parallel earnings/EW jobs upsert Cloud SQL; one parquet snapshot lands in GCS",
        40, 64, 1300, 22, size=12, bold=False, italic=True))

    # Primary chain (left to right)
    cells.append(vertex("p2_sched", "Cloud Scheduler&#xa;cron: 0 23 * * 1-5",
                        60, 130, 200, 70, "sched", bold=True))
    cells.append(vertex("p2_fmd", "fetch-market-data&#xa;Cloud Run Job",
                        320, 130, 200, 70, "fetch", bold=True))
    cells.append(vertex("p2_av", "AlphaVantage&#xa;TIME_SERIES_DAILY_ADJUSTED",
                        580, 130, 220, 70, "ext"))
    cells.append(vertex("p2_lib", "lib/indicators.py&#xa;Wilder RSI/EMA/ATR/VWAP",
                        320, 240, 200, 60, "lib"))
    cells.append(vertex("p2_sql", "Cloud SQL — market_data_daily&#xa;UPSERT ON CONFLICT (ticker, date)",
                        320, 340, 280, 70, "data", bold=True))
    cells.append(vertex("p2_gcs", "GCS bucket&#xa;raw/ OHLCV parquet snapshot",
                        680, 340, 240, 70, "data", bold=True))

    # Parallel chains
    cells.append(text("p2_parallel",
        "Parallel jobs (same scheduler fan-out, different crons):",
        60, 460, 900, 22, size=12, bold=True))
    cells.append(vertex("p2_cer", "compute-earnings-reactions&#xa;history × OHLCV → playability + archetype tags",
                        60, 500, 280, 70, "fetch"))
    cells.append(vertex("p2_ews", "evaluate-ew-strikes&#xa;score EW picks vs intraday bars",
                        60, 600, 280, 70, "fetch"))
    cells.append(vertex("p2_sql_er", "Cloud SQL — earnings_reactions",
                        420, 500, 240, 70, "data", bold=True))
    cells.append(vertex("p2_sql_ec", "Cloud SQL — earnings_calendar.ew_*",
                        420, 600, 240, 70, "data", bold=True))

    # Edges
    cells.append(edge("p2_e1", "p2_sched", "p2_fmd", "1️⃣  fires job",
                      color="#d6b656", exit_side="right", entry_side="left"))
    cells.append(edge("p2_e2", "p2_fmd", "p2_av", "2️⃣  pulls daily OHLCV for ~25 tickers",
                      color="#82b366", exit_side="right", entry_side="left"))
    cells.append(edge("p2_e3", "p2_fmd", "p2_lib", "3️⃣  computes indicators",
                      color="#9673a6", exit_side="bottom", entry_side="top", dashed=True))
    cells.append(edge("p2_e4", "p2_lib", "p2_sql", "4️⃣  upserts daily bars",
                      color="#b46504", exit_side="bottom", entry_side="top"))
    cells.append(edge("p2_e5", "p2_fmd", "p2_gcs", "5️⃣  parquet snapshot",
                      color="#b46504", dashed=True))

    cells.append(edge("p2_e6", "p2_sched", "p2_cer", "fires (separate cron)",
                      color="#d6b656", exit_side="bottom", entry_side="left", width=1))
    cells.append(edge("p2_e7", "p2_sched", "p2_ews", "fires (separate cron)",
                      color="#d6b656", exit_side="bottom", entry_side="left", width=1))
    cells.append(edge("p2_e8", "p2_cer", "p2_sql_er", "6️⃣  writes",
                      color="#b46504", exit_side="right", entry_side="left"))
    cells.append(edge("p2_e9", "p2_ews", "p2_sql_ec", "7️⃣  scores",
                      color="#b46504", exit_side="right", entry_side="left"))

    # Notes box
    cells.append(vertex("p2_note",
        "Production notes:&#xa;• Auth via Cloud SQL Connector (cloud-sql-connection-name secret)&#xa;"
        "• Watchlist resolved via gcp/fetchers/_watchlist.py (~25 tickers)&#xa;"
        "• Idempotent: re-run after partial failure converges, not duplicates&#xa;"
        "• --max-retries 0 — Cloud Run can't distinguish transient from permanent",
        700, 130, 480, 130, "white"))

    return page("🌙 Nightly Write", 1400, 800, cells)


# =============== PAGE 3 — 🌅 Morning Read ===============
def page_morning_read() -> str:
    cells = []
    cells.append(text("p3_title",
        "🌅 Daily Morning Read Path — pre-market 7-9am ET",
        40, 30, 1300, 32, size=20))
    cells.append(text("p3_sub",
        "Seven scheduled jobs prepare data and post Discord briefs before market open",
        40, 64, 1300, 22, size=12, bold=False, italic=True))

    # Timeline labels (left column)
    times = [
        ("p3_t1", "7:00 ET", 130),
        ("p3_t2", "7:00 ET", 220),
        ("p3_t3", "7:15 ET", 310),
        ("p3_t4", "8:20 ET", 400),
        ("p3_t5", "8:30 ET", 490),
        ("p3_t6", "8:45 ET", 580),
        ("p3_t7", "9:15 ET", 670),
        ("p3_t8", "9:25 ET", 760),
    ]
    for tid, label, y in times:
        cells.append(text(tid, label, 40, y, 90, 30, size=12, bold=True))

    # Jobs (middle column)
    rows = [
        ("p3_j1", "fetch-economic-events&#xa;ForexFactory + FRED → economic_events", "fetch", 130),
        ("p3_j2", "fetch-insider-transactions&#xa;Form 4 → insider_transactions", "fetch", 220),
        ("p3_j3", "fetch-earnings-calendar&#xa;EW → earnings_calendar (today's reporters)", "fetch", 310),
        ("p3_j4", "fetch-premarket-refresh&#xa;~50 tickers → gap_pct, pre_high/low/vwap", "fetch", 400),
        ("p3_j5", "premarket-brief&#xa;Strat / FTFC / levels / earnings reaction", "comp", 490),
        ("p3_j6", "insight-pipeline&#xa;multi-agent AI for SPY/IWM/QQQ → insight_runs", "comp", 580),
        ("p3_j7", "insight-discord-push&#xa;reads insight_reports → daily digest", "comp", 670),
        ("p3_j8", "signal-monitor&#xa;9:25 → 16:00 — 60s loop, CALL/PUT alerts", "comp", 760),
    ]
    for cid, val, color, y in rows:
        cells.append(vertex(cid, val, 150, y, 360, 60, color, bold=True))

    # Right column targets
    cells.append(vertex("p3_sql", "Cloud SQL&#xa;all morning tables",
                        570, 220, 200, 80, "data", bold=True))
    cells.append(vertex("p3_disc", "Discord&#xa;multi-embed brief + alerts",
                        830, 490, 220, 80, "ext", bold=True))
    cells.append(vertex("p3_anth", "Anthropic / Vertex AI",
                        830, 580, 220, 60, "async"))

    # Edges with step numbers
    cells.append(edge("p3_e1", "p3_j1", "p3_sql", "1️⃣  populates",
                      color="#b46504", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e2", "p3_j2", "p3_sql", "2️⃣  populates",
                      color="#b46504", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e3", "p3_j3", "p3_sql", "3️⃣  populates",
                      color="#b46504", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e4", "p3_j4", "p3_sql", "4️⃣  writes gap data",
                      color="#b46504", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e5_a", "p3_sql", "p3_j5", "5️⃣  reads everything",
                      color="#b46504", exit_side="bottom", entry_side="right",
                      start_arrow=False))
    cells.append(edge("p3_e5_b", "p3_j5", "p3_disc", "→ posts brief",
                      color="#5b6abf", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e6_a", "p3_j6", "p3_anth", "6️⃣  LLM calls",
                      color="#9673a6", dashed=True, exit_side="right", entry_side="left"))
    cells.append(edge("p3_e6_b", "p3_j6", "p3_sql", "writes insight_runs",
                      color="#b46504", exit_side="right", entry_side="bottom",
                      width=1))
    cells.append(edge("p3_e7", "p3_j7", "p3_disc", "7️⃣  daily digest",
                      color="#5b6abf", exit_side="right", entry_side="left"))
    cells.append(edge("p3_e8_a", "p3_j8", "p3_disc", "8️⃣  CALL/PUT alerts (loop)",
                      color="#5b6abf", exit_side="right", entry_side="left", width=2))
    cells.append(edge("p3_e8_b", "p3_j8", "p3_sql", "writes signal_alerts",
                      color="#b46504", exit_side="right", entry_side="left", width=1))

    return page("🌅 Morning Read", 1200, 870, cells)


# =============== PAGE 4 — ⚡ On-Demand Insight Refresh ===============
def page_insight_refresh() -> str:
    cells = []
    cells.append(text("p4_title",
        "⚡ On-Demand AI Insight Refresh — Cloud Tasks pipeline",
        40, 30, 1300, 32, size=20))
    cells.append(text("p4_sub",
        "User-triggered single-ticker refresh from React dashboard; isolated from scheduled batch via Cloud Tasks queue",
        40, 64, 1300, 22, size=12, bold=False, italic=True))

    cells.append(vertex("p4_browser", "Browser&#xa;React dashboard",
                        80, 150, 200, 70, "ext", bold=True))
    cells.append(vertex("p4_tp", "trading-platform&#xa;Cloud Run Service&#xa;FastAPI + React",
                        340, 150, 220, 90, "svc", bold=True))
    cells.append(vertex("p4_router", "platform/api/routers/insights.py&#xa;POST /api/insights/report/{ticker}/refresh",
                        340, 270, 320, 60, "lib"))
    cells.append(vertex("p4_ct", "Cloud Tasks Queue&#xa;insight-pipeline-queue&#xa;max-attempts=2 • dispatch=5/s",
                        340, 380, 280, 80, "async", bold=True))
    cells.append(vertex("p4_ip", "insight-pipeline Job&#xa;Cloud Run Job&#xa;env: INSIGHT_RUN_ID, INSIGHT_TICKER",
                        700, 380, 280, 80, "comp", bold=True))
    cells.append(vertex("p4_anth", "Anthropic / Vertex AI&#xa;model routing via model_routing table",
                        1020, 380, 260, 80, "async"))
    cells.append(vertex("p4_sql", "Cloud SQL&#xa;insight_reports + insight_runs",
                        700, 530, 280, 70, "data", bold=True))

    cells.append(edge("p4_e1", "p4_browser", "p4_tp", "1️⃣  click 'Refresh insight'",
                      color="#5b6abf", exit_side="right", entry_side="left"))
    cells.append(edge("p4_e2", "p4_tp", "p4_router", "2️⃣  HTTP POST",
                      color="#0e8088", exit_side="bottom", entry_side="top"))
    cells.append(edge("p4_e3", "p4_router", "p4_ct", "3️⃣  enqueue task",
                      color="#9673a6", dashed=True, exit_side="bottom", entry_side="top"))
    cells.append(edge("p4_e4", "p4_ct", "p4_ip", "4️⃣  deliver task",
                      color="#9673a6", dashed=True, exit_side="right", entry_side="left"))
    cells.append(edge("p4_e5", "p4_ip", "p4_anth", "5️⃣  multi-agent LLM",
                      color="#9673a6", exit_side="right", entry_side="left"))
    cells.append(edge("p4_e6", "p4_ip", "p4_sql", "6️⃣  writes one row",
                      color="#b46504", exit_side="bottom", entry_side="top"))

    cells.append(vertex("p4_note",
        "Why Cloud Tasks instead of inline?&#xa;"
        "• Insulates the React dashboard from minute-long agent runs&#xa;"
        "• max-attempts=2 retries transient failures only&#xa;"
        "• max-concurrent-dispatches=5 caps fan-out&#xa;"
        "• Same Job binary runs scheduled batch — env vars switch the mode",
        80, 530, 580, 130, "white"))

    return page("⚡ Insight Refresh", 1400, 720, cells)


# =============== PAGE 5 — 🚨 Failure Pipeline ===============
def page_failure_pipeline() -> str:
    cells = []
    cells.append(text("p5_title",
        "🚨 Cloud Run Job Failure Pipeline — auto GitHub issue",
        40, 30, 1300, 32, size=20))
    cells.append(text("p5_sub",
        "Any Job exiting non-zero (or logging severity≥ERROR) → labeled GitHub issue with last 50 log lines",
        40, 64, 1300, 22, size=12, bold=False, italic=True))

    cells.append(vertex("p5_job", "Cloud Run Job&#xa;exits non-zero OR logs severity≥ERROR",
                        80, 150, 280, 80, "warn", bold=True))
    cells.append(vertex("p5_sqa", "signal-quality-alarm&#xa;⚡ deliberate non-zero exit&#xa;(7d clean-rate drop &gt; 3pp)",
                        80, 260, 280, 80, "warn"))
    cells.append(vertex("p5_log", "Cloud Logging&#xa;structured logs",
                        420, 150, 220, 70, "async"))
    cells.append(vertex("p5_sink", "gcp-job-failures-sink&#xa;filter: severity≥ERROR ∧&#xa;resource.type=cloud_run_job ∧&#xa;job_name≠failure-notifier",
                        420, 250, 280, 110, "async", bold=True))
    cells.append(vertex("p5_topic", "Pub/Sub topic&#xa;gcp-job-failures",
                        760, 250, 220, 70, "async", bold=True))
    cells.append(vertex("p5_dlq", "DLQ topic&#xa;gcp-job-failures-dlq",
                        760, 340, 220, 60, "async"))
    cells.append(vertex("p5_pushsub", "Push subscription&#xa;gcp-job-failures-push",
                        1020, 250, 220, 70, "async"))
    cells.append(vertex("p5_fn", "failure-notifier&#xa;Cloud Run Service&#xa;fetches log tail, calls GitHub API",
                        1020, 360, 240, 90, "svc", bold=True))
    cells.append(vertex("p5_secrets", "Secret Manager&#xa;github-pat • github-repo",
                        1020, 470, 240, 60, "data"))
    cells.append(vertex("p5_gh", "GitHub Issue&#xa;labels: workflow-failure, automated&#xa;body: last 50 log lines + run URL",
                        1020, 560, 240, 90, "sched", bold=True))

    cells.append(edge("p5_e1", "p5_job", "p5_log", "1️⃣  emits log entry",
                      color="#b85450", exit_side="right", entry_side="left"))
    cells.append(edge("p5_e1b", "p5_sqa", "p5_log", "deliberate failure",
                      color="#b85450", exit_side="right", entry_side="left", dashed=True))
    cells.append(edge("p5_e2", "p5_log", "p5_sink", "2️⃣  filtered",
                      color="#b85450", exit_side="bottom", entry_side="top"))
    cells.append(edge("p5_e3", "p5_sink", "p5_topic", "3️⃣  publishes",
                      color="#b85450", exit_side="right", entry_side="left", dashed=True))
    cells.append(edge("p5_e4", "p5_topic", "p5_sub", "4️⃣  delivers",
                      color="#b85450", exit_side="right", entry_side="left", dashed=True))
    cells.append(edge("p5_e5", "p5_pushsub", "p5_fn", "5️⃣  push",
                      color="#b85450", exit_side="bottom", entry_side="top"))
    cells.append(edge("p5_e6a", "p5_secrets", "p5_fn", "auth",
                      color="#b46504", exit_side="top", entry_side="bottom",
                      dashed=True, width=1))
    cells.append(edge("p5_e6", "p5_fn", "p5_gh", "6️⃣  creates labeled issue",
                      color="#d6b656", exit_side="bottom", entry_side="top", width=2))

    cells.append(vertex("p5_note",
        "Why this exists:&#xa;"
        "• Replaces the old GitHub-Actions-based failure handler — Cloud Run Jobs ran outside GH&#xa;"
        "• Single issue per workflow type — duplicate failures append comments, don't spawn issues&#xa;"
        "• signal-quality-alarm reuses this pipeline as a deliberate monitoring channel",
        80, 460, 880, 110, "white"))

    return page("🚨 Failure Pipeline", 1320, 700, cells)


# =============== PAGE 6 — 💬 Discord Slash-Command ===============
def page_discord_slash() -> str:
    cells = []
    cells.append(text("p6_title",
        "💬 Discord Slash-Command Path — interactive Cloud Run Jobs",
        40, 30, 1300, 32, size=20))
    cells.append(text("p6_sub",
        "Discord interaction → discord-interactions Service → On-Demand Cloud Run Job → Discord webhook reply",
        40, 64, 1300, 22, size=12, bold=False, italic=True))

    cells.append(vertex("p6_user", "User in Discord&#xa;types /replay /backtest /validate",
                        80, 150, 240, 80, "ext", bold=True))
    cells.append(vertex("p6_di", "discord-interactions&#xa;Cloud Run Service (port 8080)&#xa;verifies via discord-public-key secret",
                        380, 150, 280, 100, "svc", bold=True))

    cells.append(vertex("p6_replay", "/replay TICKER → backfill-ticker&#xa;daily + intraday + news + indicators",
                        720, 130, 320, 70, "ond", bold=True))
    cells.append(vertex("p6_backtest", "/backtest → backtest&#xa;walk-forward via lib.backtest (2 GiB job)",
                        720, 220, 320, 70, "ond", bold=True))
    cells.append(vertex("p6_validate", "/validate → validate-brief&#xa;verifies premarket brief accuracy",
                        720, 310, 320, 70, "ond", bold=True))

    cells.append(vertex("p6_sql", "Cloud SQL&#xa;trades / signal_alerts / market_data",
                        1100, 220, 240, 70, "data", bold=True))
    cells.append(vertex("p6_disc_back", "Discord channel&#xa;via discord-webhook secret",
                        1100, 400, 240, 70, "ext", bold=True))

    cells.append(edge("p6_e1", "p6_user", "p6_di", "1️⃣  interaction (HTTP POST)",
                      color="#5b6abf", exit_side="right", entry_side="left"))
    cells.append(edge("p6_e2a", "p6_di", "p6_replay", "2️⃣  invoke via Run API",
                      color="#0e8088", exit_side="right", entry_side="left"))
    cells.append(edge("p6_e2b", "p6_di", "p6_backtest", "2️⃣  invoke via Run API",
                      color="#0e8088", exit_side="right", entry_side="left"))
    cells.append(edge("p6_e2c", "p6_di", "p6_validate", "2️⃣  invoke via Run API",
                      color="#0e8088", exit_side="right", entry_side="left"))
    cells.append(edge("p6_e3a", "p6_replay", "p6_sql", "3️⃣  fetches/writes",
                      color="#b46504", exit_side="right", entry_side="top",
                      start_arrow=True, width=1))
    cells.append(edge("p6_e3b", "p6_backtest", "p6_sql", "3️⃣  reads",
                      color="#b46504", exit_side="right", entry_side="left", width=1))
    cells.append(edge("p6_e3c", "p6_validate", "p6_sql", "3️⃣  reads",
                      color="#b46504", exit_side="right", entry_side="bottom", width=1))
    cells.append(edge("p6_e4a", "p6_replay", "p6_disc_back", "4️⃣  posts result",
                      color="#5b6abf", exit_side="right", entry_side="top"))
    cells.append(edge("p6_e4b", "p6_backtest", "p6_disc_back", "4️⃣  posts result",
                      color="#5b6abf", exit_side="right", entry_side="left"))
    cells.append(edge("p6_e4c", "p6_validate", "p6_disc_back", "4️⃣  posts result",
                      color="#5b6abf", exit_side="right", entry_side="left"))

    cells.append(vertex("p6_note",
        "Two Discord secrets — different purposes:&#xa;"
        "• discord-public-key — verifies INCOMING interactions are signed by Discord&#xa;"
        "• discord-webhook — Job posts OUTGOING messages back to a channel",
        80, 280, 600, 90, "white"))

    return page("💬 Discord Slash-Cmd", 1400, 520, cells)


# =============== PAGE 7 — 🎯 Earnings Pipeline ===============
def page_earnings_pipeline() -> str:
    cells = []
    cells.append(text("p7_title",
        "🎯 Earnings Pipeline — calendar, reactions, post-earnings playability",
        40, 30, 1400, 32, size=20))
    cells.append(text("p7_sub",
        "Weekly AV history backfill + daily EW calendar + nightly reactions/strikes computations feed the 8:30 ET premarket-brief",
        40, 64, 1400, 22, size=12, bold=False, italic=True))

    # Column headers
    cells.append(text("p7_h1", "Schedule",  60, 105, 160, 20, size=11, bold=True))
    cells.append(text("p7_h2", "Cloud Run Job", 240, 105, 240, 20, size=11, bold=True))
    cells.append(text("p7_h3", "External / Reads", 500, 105, 240, 20, size=11, bold=True))
    cells.append(text("p7_h4", "Cloud SQL Write Target", 760, 105, 260, 20, size=11, bold=True))
    cells.append(text("p7_h5", "Consumer", 1080, 105, 260, 20, size=11, bold=True))

    # === Lane 1: Weekly history backfill ===
    cells.append(vertex("p7_l1_sched", "1️⃣  Cloud Scheduler&#xa;weekly cron",
                        60, 130, 160, 70, "sched", bold=True))
    cells.append(vertex("p7_l1_job", "fetch-earnings-history&#xa;chains _run_backfill() post-fetch",
                        240, 130, 240, 70, "fetch", bold=True))
    cells.append(vertex("p7_l1_av", "AlphaVantage EARNINGS&#xa;quarterly history",
                        500, 130, 240, 70, "ext"))
    cells.append(vertex("p7_l1_tbl", "earnings_history&#xa;ticker × fiscal_quarter",
                        760, 130, 260, 70, "data", bold=True))

    # === Lane 2: Daily EW calendar pull ===
    cells.append(vertex("p7_l2_sched", "2️⃣  Cloud Scheduler&#xa;daily 7:15 ET",
                        60, 230, 160, 70, "sched", bold=True))
    cells.append(vertex("p7_l2_job", "fetch-earnings-calendar&#xa;EW credentials → today's reporters",
                        240, 230, 240, 70, "fetch", bold=True))
    cells.append(vertex("p7_l2_ew", "Earnings Whispers&#xa;calendar + recommended strikes",
                        500, 230, 240, 70, "ext"))
    cells.append(vertex("p7_l2_tbl", "earnings_calendar&#xa;today's reporters + recommended strikes",
                        760, 230, 260, 70, "data", bold=True))

    # === Lane 3: Reactions computation ===
    cells.append(vertex("p7_l3_sched", "3️⃣  Cloud Scheduler&#xa;nightly post-close",
                        60, 330, 160, 70, "sched", bold=True))
    cells.append(vertex("p7_l3_job", "compute-earnings-reactions&#xa;lib.earnings_reactions",
                        240, 330, 240, 70, "fetch", bold=True))
    cells.append(vertex("p7_l3_in", "reads earnings_history&#xa;× market_data_daily",
                        500, 330, 240, 70, "data"))
    cells.append(vertex("p7_l3_tbl", "earnings_reactions&#xa;playability + archetype tags",
                        760, 330, 260, 70, "data", bold=True))

    # === Lane 4: EW strikes scoring ===
    cells.append(vertex("p7_l4_sched", "4️⃣  Cloud Scheduler&#xa;nightly post-close",
                        60, 430, 160, 70, "sched", bold=True))
    cells.append(vertex("p7_l4_job", "evaluate-ew-strikes&#xa;score EW picks vs intraday bars",
                        240, 430, 240, 70, "fetch", bold=True))
    cells.append(vertex("p7_l4_in", "reads earnings_calendar&#xa;× market_data_intraday",
                        500, 430, 240, 70, "data"))
    cells.append(vertex("p7_l4_tbl", "earnings_calendar.ew_*&#xa;UPDATE in-place per ticker × date",
                        760, 430, 260, 70, "data", bold=True))

    # === Lane 5: Consumer ===
    cells.append(vertex("p7_l5_sched", "5️⃣  Cloud Scheduler&#xa;daily 8:30 ET",
                        60, 530, 160, 70, "sched", bold=True))
    cells.append(vertex("p7_l5_job", "premarket-brief&#xa;conditional_lean_summary embed",
                        240, 530, 240, 70, "comp", bold=True))
    cells.append(vertex("p7_l5_in", "reads earnings_reactions&#xa;+ earnings_calendar",
                        500, 530, 240, 70, "data"))
    cells.append(vertex("p7_l5_tbl", "premarket_analysis&#xa;persists embed for audit trail",
                        760, 530, 260, 70, "data"))
    cells.append(vertex("p7_l5_disc", "Discord brief embed&#xa;post-earnings reaction profile",
                        1080, 530, 280, 70, "ext", bold=True))

    # Edges per lane
    for i, lane in enumerate(["l1", "l2", "l3", "l4"], start=1):
        cells.append(edge(f"p7_e{i}_a", f"p7_{lane}_sched", f"p7_{lane}_job",
                          "fires", color="#d6b656",
                          exit_side="right", entry_side="left"))
        api_or_in = f"p7_{lane}_av" if lane == "l1" else (f"p7_{lane}_ew" if lane == "l2" else f"p7_{lane}_in")
        edge_color = "#82b366" if lane in ("l1", "l2") else "#b46504"
        edge_label = "pulls" if lane in ("l1", "l2") else "joins"
        cells.append(edge(f"p7_e{i}_b", f"p7_{lane}_job", api_or_in,
                          edge_label, color=edge_color,
                          exit_side="right", entry_side="left",
                          start_arrow=(lane in ("l3", "l4"))))
        cells.append(edge(f"p7_e{i}_c", f"p7_{lane}_job", f"p7_{lane}_tbl",
                          "writes", color="#b46504",
                          exit_side="right", entry_side="bottom"
                          if lane in ("l3", "l4") else "left"))

    # Lane 5 (consumer) edges
    cells.append(edge("p7_e5_a", "p7_l5_sched", "p7_l5_job", "fires",
                      color="#d6b656", exit_side="right", entry_side="left"))
    cells.append(edge("p7_e5_b", "p7_l5_job", "p7_l5_in", "reads",
                      color="#b46504", exit_side="right", entry_side="left",
                      start_arrow=True))
    cells.append(edge("p7_e5_c", "p7_l5_job", "p7_l5_tbl", "writes",
                      color="#b46504", exit_side="bottom", entry_side="top",
                      width=1))
    cells.append(edge("p7_e5_d", "p7_l5_job", "p7_l5_disc",
                      "6️⃣  posts reaction profile", color="#5b6abf",
                      exit_side="right", entry_side="left", width=2))

    # Cross-lane references (table → next-lane reads, dotted)
    cells.append(edge("p7_x1", "p7_l1_tbl", "p7_l3_in", "feeds",
                      color="#b46504", dashed=True, width=1,
                      exit_side="bottom", entry_side="top"))
    cells.append(edge("p7_x2", "p7_l2_tbl", "p7_l4_in", "feeds",
                      color="#b46504", dashed=True, width=1,
                      exit_side="bottom", entry_side="top"))
    cells.append(edge("p7_x3", "p7_l3_tbl", "p7_l5_in", "feeds",
                      color="#b46504", dashed=True, width=1,
                      exit_side="bottom", entry_side="top"))

    # Notes
    cells.append(vertex("p7_warn",
        "⚠ fetch-earnings-options Job&#xa;CONFIRMED BROKEN — module gcp.fetchers.fetch_earnings_options does not exist.&#xa;"
        "No scheduler binding, every execution would ModuleNotFoundError. Safe to delete (per ARCHITECTURE.md reconciliation).",
        60, 640, 660, 80, "warn"))
    cells.append(vertex("p7_note",
        "Why earnings has its own page:&#xa;"
        "• Two-source pipeline (AV history + EW calendar) join into one analytical product&#xa;"
        "• premarket-brief 'conditional lean' is the consumer's main deliverable&#xa;"
        "• EW strikes scoring is the only place options-level fidelity is measured per-ticker daily",
        740, 640, 620, 100, "white"))

    return page("🎯 Earnings Pipeline", 1500, 780, cells)


# =============== ASSEMBLE ===============
def main():
    content = PATH.read_text(encoding="utf-8")

    # Strip pages 2+ (idempotent re-run).
    first_diagram_end = content.find("</diagram>")
    if first_diagram_end == -1:
        raise SystemExit("could not find first </diagram> — aborting")
    head = content[: first_diagram_end + len("</diagram>")]
    tail = content[first_diagram_end + len("</diagram>"):]
    # tail should be just \n</mxfile>\n possibly with whitespace + other diagrams
    new_content = head + "\n"
    new_content += page_nightly_write() + "\n"
    new_content += page_morning_read() + "\n"
    new_content += page_insight_refresh() + "\n"
    new_content += page_failure_pipeline() + "\n"
    new_content += page_discord_slash() + "\n"
    new_content += page_earnings_pipeline() + "\n"
    new_content += "</mxfile>\n"

    PATH.write_text(new_content, encoding="utf-8")
    print("wrote 6 process pages")


if __name__ == "__main__":
    main()
