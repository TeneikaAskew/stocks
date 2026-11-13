"""Tests for scripts/maintenance/canvas_from_export.py (FEAT-CICD-001)."""
from __future__ import annotations

import base64
import gzip
import json
import re
import subprocess
import sys

import pytest

from scripts.maintenance import canvas_from_export as cfe

ROOT_JS = """(function(){
const J = (name, sched, note, reads, writes, module, res, surface) => ({ name, sched, note, reads, writes, module, res, surface });
const JOBS = {
  fetch: [
    J('fetch-a', 'Weekdays 07:00 ET', 'Fetches A.', 'api', 'a_table', undefined, '512 MiB', 'Brief'),
    J('fetch-old', 'Weekdays 23:00 ET', 'Retired fetcher.', 'api', 'old_table', undefined, '512 MiB', 'Brief'),
  ],
  compute: [
    J('compute-b', 'On demand', 'Computes B.', 'a_table', 'b_table', undefined, '1 GiB', 'Report'),
    J('compute-c', 'Scheduled', 'Computes C.', 'a_table', 'c_table', undefined, '1 GiB', 'Report'),
  ],
};

// Cloud Scheduler triggers as declared in gcp/deploy.sh deploy_schedulers() (HEAD, 2026-09-07). Old note.
const C = (name, cron, job, args) => ({ name, cron, job, args });
const CRONS = [
  C('fetch-a-daily', '0 7 * * 1-5', 'fetch-a'),
  C('fetch-old-daily', '0 23 * * 1-5', 'fetch-old'),
  C('compute-c-daily', '0 1 * * 2-6', 'compute-c', 'short'),
  C('reconcile-hourly', '0 * * * *', 'svc-n', '/reconcile'),
];
const DETAILS = { fetch_old: { title: 'fetch-old', summary: 'fetch-old feeds old_table.' } };
window.ARCH_DETAILS = { JOBS: JOBS, CRONS: CRONS, DETAILS: DETAILS };
})();
"""

TEMPLATE = "<!DOCTYPE html><html><head></head><body><div>svc-n</div><script>x</script></body></html>"


def bundle_html(js: str = ROOT_JS) -> str:
    manifest = {
        "11111111-1111-1111-1111-111111111111": {"mime": "image/svg+xml", "compressed": False,
                                                 "data": base64.b64encode(b"<svg/>").decode()},
        "22222222-2222-2222-2222-222222222222": {"mime": "text/javascript", "compressed": True,
                                                 "data": base64.b64encode(gzip.compress(js.encode(), mtime=0)).decode()},
    }
    tpl = json.dumps(TEMPLATE, ensure_ascii=False).replace("</", "<\\u002F")
    return ("<!DOCTYPE html>\n<html><head><title>Bundled Page</title></head><body>\n"
            "<script>/* loader */</script>\n"
            f'<script type="__bundler/manifest">\n{json.dumps(manifest, separators=(",", ":"))}\n</script>\n'
            f'<script type="__bundler/template">\n{tpl}\n</script>\n</body></html>\n')


def job(name, kind="compute", schedules=(), module=None, reads=(), writes=()):
    return {"name": name, "kind": kind, "declared": True, "live": None, "module": module,
            "reads": list(reads), "writes": list(writes), "possible_reads": {}, "possible_writes": {},
            "resources": {"memory": "1Gi", "timeout": "600", "cpu": "1", "retries": "0"},
            "schedules": [{"name": s, "cron": c, "args": None} for s, c in schedules],
            "deploy_function": "deploy_" + name.replace("-", "_")}


def sched(name, cron, target, args=None, kind="job", uri=None):
    return {"name": name, "cron": cron, "args": args, "declared": True, "live": None,
            "target": {"kind": kind, "name": target, "uri": uri}, "time_zone": "America/New_York"}


def export(**over):
    data = {
        "schema": "architecture-export/1",
        "sources": {"commit": "f186880672db26165da8c09b63e56ae2b7909c17", "files": {}, "live": None},
        "jobs": [
            job("fetch-a", "fetcher", [("fetch-a-daily", "0 7 * * 1-5")]),
            job("compute-b", schedules=[("compute-b-weekly", "0 5 * * 0")]),
            job("compute-c", schedules=[("compute-c-daily", "30 1 * * 2-6")]),
            job("fetch-new", "fetcher", module="gcp.fetchers.fetch_new", reads=["api"], writes=["new_table"]),
        ],
        "schedulers": [
            sched("fetch-a-daily", "0 7 * * 1-5", "fetch-a"),
            sched("compute-c-daily", "30 1 * * 2-6", "compute-c", "--full"),
            sched("reconcile-hourly", "0 * * * *", "svc-n", kind="service", uri="${service_url}/reconcile"),
            sched("compute-b-weekly", "0 5 * * 0", "compute-b"),
        ],
        "services": [{"name": "svc-n", "declared": True, "live": None},
                     {"name": "svc-new", "declared": True, "live": None}],
        "tables": [{"name": "a_table", "kind": "table"}, {"name": "zz_unnamed", "kind": "table"}],
        "counts": {}, "drift": {"declared_not_live": [], "live_not_declared": [], "paused_schedulers": []},
    }
    data.update(over)
    return data


def crons(js):
    return re.findall(r"^  C\((.*)\),$", js, re.MULTILINE)


def test_crons_rebuilt_from_export_in_page_order():
    res = cfe.update(ROOT_JS, export())
    assert crons(res.js) == [
        "'fetch-a-daily', '0 7 * * 1-5', 'fetch-a'",
        "'compute-c-daily', '30 1 * * 2-6', 'compute-c', '--full'",
        "'reconcile-hourly', '0 * * * *', 'svc-n', '/reconcile'",
        "'compute-b-weekly', '0 5 * * 0', 'compute-b'",
    ]
    assert res.crons_added == ["compute-b-weekly"]
    assert res.crons_removed == ["fetch-old-daily"]
    assert [n for n, _, _ in res.crons_changed] == ["compute-c-daily"]


def test_service_trigger_without_args_keeps_its_path():
    res = cfe.update(ROOT_JS, export())
    assert "C('reconcile-hourly', '0 * * * *', 'svc-n', '/reconcile')," in res.js
    assert "reconcile-hourly" not in [n for n, _, _ in res.crons_changed]


def test_cards_for_undeclared_jobs_are_removed_and_reported_where_still_named():
    res = cfe.update(ROOT_JS, export())
    assert "J('fetch-old'" not in res.js
    assert res.cards_removed == ["fetch-old"]
    assert res.stale_mentions == [("fetch-old", 2)]  # DETAILS title and summary, never rewritten
    assert "fetch-old feeds old_table." in res.js


def test_stub_card_added_for_a_declared_job_the_page_never_names():
    res = cfe.update(ROOT_JS, export())
    assert res.cards_added == ["fetch-new"]
    fetch_group = res.js[res.js.index("  fetch: ["):res.js.index("  compute: [")]
    assert "J('fetch-new', 'On demand · 1 GiB / 10 min', 'Declared in gcp/deploy.sh; not yet described on this page.', " \
           "'api', 'new_table', 'gcp/fetchers/fetch_new.py', '1 GiB / 10 min', '—')," in fetch_group


def test_a_job_named_elsewhere_on_the_page_gets_no_stub():
    data = export()
    data["jobs"].append(job("svc-ish"))
    js = ROOT_JS.replace("old_table.' } };", "old_table.' }, x: { title: 'svc-ish' } };")
    assert "svc-ish" not in cfe.update(js, data).cards_added


def test_schedule_text_that_contradicts_triggers_is_reported_not_rewritten():
    res = cfe.update(ROOT_JS, export())
    flagged = {n: s for n, s, _ in res.labels_to_check}
    assert flagged == {"compute-b": "On demand"}          # on demand, yet a weekly trigger
    assert "J('compute-b', 'On demand'," in res.js         # prose untouched
    assert "compute-c" not in flagged                      # "Scheduled" is generic, never flagged


@pytest.mark.parametrize("label,crons_,bad", [
    ("Weekdays 07:00 ET", ["0 7 * * 1-5"], False),
    ("Weekdays 07:00 ET", ["30 7 * * 1-5"], True),
    ("Hourly 08:00–17:00 ET weekdays", ["0 8-17 * * 1-5"], False),
    ("Weekdays 07:00 · 10:00 · 13:00 · 17:00 ET", ["0 7,10,13,17 * * 1-5"], False),
    ("Mon–Sat 02:30 ET", ["30 2 * * 1-6", "0 3 * * 0"], True),
    ("After close", ["0 22 * * 1-5"], False),
    ("One-shot", ["0 5 1 * *"], True),
    ("On demand", [], False),
])
def test_label_disagrees(label, crons_, bad):
    assert cfe.label_disagrees(label, crons_) is bad


def test_stamp_names_the_export_commit():
    res = cfe.update(ROOT_JS, export(), run_label="run 1")
    assert ("// Cloud Scheduler triggers as declared in gcp/deploy.sh deploy_schedulers() at main f1868806, "
            "from the architecture export (run 1).") in res.js
    assert "2026-09-07" not in res.js


def test_second_run_changes_nothing():
    first = cfe.update(ROOT_JS, export(), run_label="run 1")
    second = cfe.update(first.js, export(), run_label="run 1")
    assert second.js == first.js
    assert not second.changed


def test_unnamed_services_and_tables_reported():
    res = cfe.update(ROOT_JS, export())
    assert res.services_not_named == ["svc-new"]
    assert res.tables_not_named == ["zz_unnamed"]


def test_undeclared_rows_are_ignored():
    data = export()
    data["jobs"][0] = dict(data["jobs"][0], declared=False)  # live only: not drawn
    res = cfe.update(ROOT_JS, data)
    assert "fetch-a" in res.cards_removed


def test_bad_export_refused():
    with pytest.raises(cfe.CanvasError):
        cfe.update(ROOT_JS, export(schema="other/1"))
    with pytest.raises(cfe.CanvasError):
        cfe.update(ROOT_JS, export(sources={"commit": None}))


def test_page_without_data_asset_refused():
    with pytest.raises(cfe.CanvasError):
        cfe.Bundle.parse("<html></html>")
    with pytest.raises(cfe.CanvasError):
        cfe.Bundle.parse(bundle_html("const nothing = 1;"))


def test_render_changes_only_the_data_asset():
    html = bundle_html()
    b = cfe.Bundle.parse(html)
    res = cfe.update(b.js, export())
    out = b.render(res.js)
    strip = lambda h: re.sub(r'(<script type="__bundler/manifest">).*?(</script>)', r"\1\2", h, flags=re.DOTALL)
    assert strip(out) == strip(html)
    nb = cfe.Bundle.parse(out)
    assert nb.js == res.js
    assert nb.manifest["11111111-1111-1111-1111-111111111111"] == b.manifest["11111111-1111-1111-1111-111111111111"]


def test_cli_writes_page_and_report_and_check_mode(tmp_path):
    page, exp = tmp_path / "page.html", tmp_path / "export.json"
    page.write_text(bundle_html(), encoding="utf-8")
    exp.write_text(json.dumps(export()), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, "-m", "scripts.maintenance.canvas_from_export",
                                     "--export", str(exp), *a], capture_output=True, text=True, check=False)
    chk = run("--canvas", str(page), "--check")
    assert chk.returncode == 1 and "compute-b-weekly" in chk.stdout
    out, rep = tmp_path / "out.html", tmp_path / "report.md"
    ok = run("--canvas", str(page), "--output", str(out), "--report", str(rep))
    assert ok.returncode == 0, ok.stderr
    text = rep.read_text(encoding="utf-8")
    assert "### Applied: job cards removed (no longer declared)\n- `fetch-old`" in text
    assert "`compute-b`: says “On demand”" in text
    assert "svc-new" in text and "zz_unnamed" in text
    again = run("--canvas", str(out), "--check")
    assert again.returncode == 0, again.stdout


def test_cli_refusal_exits_2_and_writes_nothing(tmp_path):
    page, exp, out = tmp_path / "page.html", tmp_path / "export.json", tmp_path / "out.html"
    page.write_text("<html>no data asset</html>", encoding="utf-8")
    exp.write_text(json.dumps(export()), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, "-m", "scripts.maintenance.canvas_from_export",
                                     "--export", str(exp), *a], capture_output=True, text=True, check=False)
    for args in (("--canvas", str(page), "--output", str(out)),
                 ("--canvas", str(page), "--check"),
                 ("--canvas", str(tmp_path / "missing.html"), "--check")):
        res = run(*args)
        assert res.returncode == 2, (args, res.stdout, res.stderr)
        assert "refused" in res.stderr
    exp.write_text("[]", encoding="utf-8")
    page.write_text(bundle_html(), encoding="utf-8")
    assert run("--canvas", str(page), "--output", str(out)).returncode == 2
    assert not out.exists()


# Codex round 1 on #1860 ─────────────────────────────────────────────────────

def test_a_provenance_only_change_is_reported_as_applied():
    first = cfe.update(ROOT_JS, export(), run_label="run 1")
    second = cfe.update(first.js, export(), run_label="run 2")
    assert second.changed and second.stamp_changed
    assert not (second.crons_added or second.crons_changed or second.cards_added)
    text = cfe.report(second, export())
    assert "### Applied: provenance comment\n- `" in text and "(run 2)" in text.split("### Applied: provenance comment")[1]
    assert "### Applied: provenance comment\n- none" in cfe.report(cfe.update(first.js, export(), "run 1"), export())


@pytest.mark.parametrize("label,crons_,bad", [
    ("Hourly 08:00–17:00 ET weekdays", ["0 * * * 1-5"], False),
    ("Every 5 min 09:30–15:55 ET", ["*/5 9-15 * * 1-5"], False),
    ("Every 5 min 09:32 ET", ["*/5 9-15 * * 1-5"], True),
    ("Weekdays 07:00 ET", ["0 7 * * 1-5", "0 L * * *"], False),  # unknown form: never "wrong"
])
def test_wildcard_and_stepped_crons_are_expanded(label, crons_, bad):
    assert cfe.label_disagrees(label, crons_) is bad


def test_a_new_scheduled_job_gets_a_stub_even_though_its_trigger_is_added():
    data = export()
    data["jobs"].append(job("fetch-brand-new", "fetcher", [("fetch-brand-new-daily", "0 6 * * 1-5")]))
    data["schedulers"].append(sched("fetch-brand-new-daily", "0 6 * * 1-5", "fetch-brand-new"))
    res = cfe.update(ROOT_JS, data)
    assert "fetch-brand-new-daily" in res.crons_added
    assert "fetch-brand-new" in res.cards_added
    assert "J('fetch-brand-new', 'Scheduled" in res.js
    assert cfe.update(res.js, data).cards_added == []


def test_crlf_page_keeps_its_line_endings(tmp_path):
    page, exp, out = tmp_path / "page.html", tmp_path / "export.json", tmp_path / "out.html"
    html = bundle_html().replace("\n", "\r\n")
    page.write_bytes(html.encode("utf-8"))
    exp.write_text(json.dumps(export()), encoding="utf-8")
    res = subprocess.run([sys.executable, "-m", "scripts.maintenance.canvas_from_export", "--export", str(exp),
                          "--canvas", str(page), "--output", str(out), "--report", str(tmp_path / "r.md")],
                         capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    strip = lambda b: re.sub(rb'(<script type="__bundler/manifest">).*?(</script>)', rb"\1\2", b, flags=re.DOTALL)
    assert strip(out.read_bytes()) == strip(page.read_bytes())
    assert out.read_bytes().count(b"\r\n") == html.count("\r\n")


def test_an_empty_trigger_list_stays_readable():
    data = export(schedulers=[])
    first = cfe.update(ROOT_JS, data)
    assert "const CRONS = [\n];" in first.js
    second = cfe.update(first.js, data)
    assert second.js == first.js and not second.changed


def test_a_card_split_over_lines_is_refused():
    js = ROOT_JS.replace("J('fetch-old', 'Weekdays 23:00 ET',", "J('fetch-old', 'Weekdays 23:00 ET',\n     ")
    with pytest.raises(cfe.CanvasError, match="not on one line"):
        cfe.update(js, export())


@pytest.mark.parametrize("damage", ["truncated", "not_base64", "not_gzip"])
def test_a_damaged_asset_is_refused_with_exit_2(tmp_path, damage):
    html = bundle_html()
    m = re.search(r'<script type="__bundler/manifest">\n(.*?)\n</script>', html, re.DOTALL)
    manifest = json.loads(m.group(1))
    entry = manifest["22222222-2222-2222-2222-222222222222"]
    raw = base64.b64decode(entry["data"])
    if damage == "truncated":
        entry["data"] = base64.b64encode(raw[:-8]).decode()
    elif damage == "not_base64":
        entry["data"] = "!!!not base64!!!"
    else:
        entry["data"] = base64.b64encode(b"plain bytes, not gzip").decode()
    page, exp, out = tmp_path / "page.html", tmp_path / "export.json", tmp_path / "out.html"
    page.write_text(html[:m.start(1)] + json.dumps(manifest, separators=(",", ":")) + html[m.end(1):],
                    encoding="utf-8")
    exp.write_text(json.dumps(export()), encoding="utf-8")
    for args in (("--output", str(out)), ("--check",)):
        res = subprocess.run([sys.executable, "-m", "scripts.maintenance.canvas_from_export",
                              "--export", str(exp), "--canvas", str(page), *args],
                             capture_output=True, text=True, check=False)
        assert res.returncode == 2, (damage, args, res.stderr)
        assert "refused" in res.stderr and "Traceback" not in res.stderr
    assert not out.exists()
