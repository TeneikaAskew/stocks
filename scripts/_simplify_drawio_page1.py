"""Drop the ~58 fine-grained edges on Page 1 of Architecture.drawio and
replace them with ~25 swimlane-level edges. The architecture diagram
shows GROUPS, not individual wires; per-row detail belongs on the
per-process pages.

Run:  py scripts/_simplify_drawio_page1.py
"""

from __future__ import annotations
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "Architecture.drawio"
content = PATH.read_text(encoding="utf-8")

# 1. Strip every existing edge cell. Edges are <mxCell ... edge="1" ...>
#    with one <mxGeometry ...> child (sometimes nested with waypoints).
edge_re = re.compile(
    r'\n\s*<mxCell\b[^>]*\bedge="1"[^>]*>[\s\S]*?</mxCell>',
    re.MULTILINE,
)
removed = len(edge_re.findall(content))
content = edge_re.sub("", content)
print(f"removed {removed} edges")

# 2. Define the new edge set. Each tuple:
#    (id, source_id, target_id, style_extras)
# style_extras goes after the common prefix. Anchor hints are
# computed in step 3.
EDGES = [
    # External APIs feed Fetchers (single combined edge from group to group)
    ("e_ext_fetch", "ext_group", "fetch_group", "strokeColor=#82b366;strokeWidth=2;"),
    # Cloud Scheduler fires both Job columns
    ("e_sched_fetch", "sched_group", "fetch_group", "strokeColor=#d6b656;strokeWidth=2;"),
    ("e_sched_comp", "sched_group", "comp_group", "strokeColor=#d6b656;strokeWidth=2;"),
    # Fetchers write to data plane
    ("e_fetch_sql", "fetch_group", "sql_box", "strokeColor=#b46504;strokeWidth=2;"),
    ("e_fetch_gcs", "fetch_group", "gcs_box", "dashed=1;strokeColor=#b46504;"),
    # Compute jobs read+write SQL, post to Discord, call LLMs
    ("e_comp_sql", "comp_group", "sql_box", "startArrow=classic;startFill=1;strokeColor=#b46504;strokeWidth=2;"),
    ("e_comp_disc", "comp_group", "ext_discord", "strokeColor=#5b6abf;strokeWidth=2;"),
    ("e_comp_vertex", "comp_group", "vertex_box", "dashed=1;strokeColor=#9673a6;"),
    # On-Demand jobs (Discord-triggered + Cloud Tasks-triggered)
    ("e_disc_di", "ext_discord", "svc_di", "strokeColor=#5b6abf;strokeWidth=2;"),
    ("e_di_ond", "svc_di", "ond_group", "strokeColor=#0e8088;strokeWidth=2;"),
    ("e_ond_sql", "ond_group", "sql_box", "strokeColor=#b46504;"),
    ("e_ond_disc", "ond_group", "ext_discord", "strokeColor=#5b6abf;"),
    # Browser → React UI → SQL + Cloud Tasks
    ("e_browser_tp", "ext_browser", "svc_tp", "strokeColor=#5b6abf;strokeWidth=2;"),
    ("e_tp_sql", "svc_tp", "sql_box", "startArrow=classic;startFill=1;strokeColor=#0e8088;strokeWidth=2;"),
    ("e_tp_ct", "svc_tp", "ct_box", "dashed=1;strokeColor=#9673a6;strokeWidth=2;"),
    ("e_ct_comp", "ct_box", "comp_group", "dashed=1;strokeColor=#9673a6;strokeWidth=2;"),
    # Failure pipeline: jobs → sink → topic → notifier → GitHub
    ("e_jobs_sink", "comp_group", "sink_box", "dashed=1;strokeColor=#b85450;"),
    ("e_fetch_sink", "fetch_group", "sink_box", "dashed=1;strokeColor=#b85450;"),
    ("e_sink_ps", "sink_box", "ps_topic", "dashed=1;strokeColor=#b85450;strokeWidth=2;"),
    ("e_ps_fn", "ps_topic", "svc_fn", "dashed=1;strokeColor=#b85450;strokeWidth=2;"),
    ("e_fn_gh", "svc_fn", "ext_gh", "strokeColor=#b85450;strokeWidth=2;"),
    # Shared lib/ imports (dotted)
    ("e_lib_comp", "lib_group", "comp_group", "dashed=1;dashPattern=1 4;strokeColor=#9673a6;"),
    ("e_lib_ond", "lib_group", "ond_group", "dashed=1;dashPattern=1 4;strokeColor=#9673a6;"),
    ("e_lib_tp", "lib_group", "svc_tp", "dashed=1;dashPattern=1 4;strokeColor=#9673a6;"),
    ("e_lib_fetch", "lib_group", "fetch_group", "dashed=1;dashPattern=1 4;strokeColor=#9673a6;"),
    # Secrets injection (one summary line)
    ("e_sec_jobs", "sec_box", "fetch_group", "dashed=1;strokeColor=#b46504;"),
    ("e_sec_svc", "sec_box", "svc_group", "dashed=1;strokeColor=#b46504;"),
    # GitHub Actions ↔ SQL via db-query.yml + deploy → Pages
    ("e_dbq_sql", "gha_dbq", "sql_box", "startArrow=classic;startFill=1;strokeColor=#d6b656;"),
    ("e_dep_pages", "gha_dep", "ext_ghpages", "strokeColor=#d6b656;"),
]

# 3. Parse vertex geometries to compute exit/entry anchors (same logic
#    as the prior routing script).
vertices: dict[str, tuple[float, float, float, float]] = {}
cell_re = re.compile(
    r'<mxCell\s+id="([^"]+)"[^>]*\svertex="1"[^>]*>\s*'
    r'<mxGeometry\s+([^/]*?)\s*as="geometry"\s*/>',
    re.DOTALL,
)
attr_re = re.compile(r'(\w+)="([\d.\-]+)"')
for m in cell_re.finditer(content):
    cid = m.group(1)
    a = dict(attr_re.findall(m.group(2)))
    try:
        vertices[cid] = (float(a["x"]), float(a["y"]), float(a["width"]), float(a["height"]))
    except KeyError:
        continue


def anchors(sid: str, tid: str) -> str:
    if sid not in vertices or tid not in vertices:
        return ""
    sx, sy, sw, sh = vertices[sid]
    tx, ty, tw, th = vertices[tid]
    scx, scy = sx + sw / 2, sy + sh / 2
    tcx, tcy = tx + tw / 2, ty + th / 2
    dx, dy = tcx - scx, tcy - scy
    horiz_overlap = not (tx + tw < sx or sx + sw < tx)
    vert_overlap = not (ty + th < sy or sy + sh < ty)
    if horiz_overlap and not vert_overlap:
        return f"exitX=0.5;exitY={1 if dy > 0 else 0};exitDx=0;exitDy=0;entryX=0.5;entryY={0 if dy > 0 else 1};entryDx=0;entryDy=0;"
    if vert_overlap and not horiz_overlap:
        return f"exitX={1 if dx > 0 else 0};exitY=0.5;exitDx=0;exitDy=0;entryX={0 if dx > 0 else 1};entryY=0.5;entryDx=0;entryDy=0;"
    if abs(dy) >= abs(dx):
        return f"exitX=0.5;exitY={1 if dy > 0 else 0};exitDx=0;exitDy=0;entryX=0.5;entryY={0 if dy > 0 else 1};entryDx=0;entryDy=0;"
    return f"exitX={1 if dx > 0 else 0};exitY=0.5;exitDx=0;exitDy=0;entryX={0 if dx > 0 else 1};entryY=0.5;entryDx=0;entryDy=0;"


# 4. Emit edge XML and inject before the first </root>.
common = "endArrow=classic;html=1;edgeStyle=orthogonalEdgeStyle;rounded=1;jettySize=auto;orthogonalLoop=1;"
new_xml: list[str] = []
for eid, sid, tid, extras in EDGES:
    if sid not in vertices or tid not in vertices:
        print(f"  skip {eid}: missing {sid if sid not in vertices else tid}")
        continue
    style = anchors(sid, tid) + common + extras
    new_xml.append(
        f'                <mxCell id="{eid}" style="{style}" edge="1" parent="1" '
        f'source="{sid}" target="{tid}">\n'
        f'                    <mxGeometry relative="1" as="geometry"/>\n'
        f'                </mxCell>'
    )
print(f"adding {len(new_xml)} edges")

# Insert before the first </root> (page 1).
inject = "\n" + "\n".join(new_xml) + "\n            "
content = content.replace("            </root>", inject + "</root>", 1)
PATH.write_text(content, encoding="utf-8")
print("done")
