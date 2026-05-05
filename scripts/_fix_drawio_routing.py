"""One-shot helper: inject exit/entry anchor hints into every edge of
Architecture.drawio so orthogonal connectors leave from the correct
side of the source box and arrive at the correct side of the target
box. Eliminates the spaghetti-line look without needing to open drawio.

Run:  py scripts/_fix_drawio_routing.py
"""

import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "Architecture.drawio"

content = PATH.read_text(encoding="utf-8")

# 1. Parse every vertex's geometry. Attribute order varies, so use a
#    permissive regex that tolerates whatever drawio wrote.
vertices: dict[str, tuple[float, float, float, float]] = {}

cell_re = re.compile(
    r'<mxCell\s+id="([^"]+)"[^>]*\svertex="1"[^>]*>\s*'
    r'<mxGeometry\s+([^/]*?)\s*as="geometry"\s*/>',
    re.DOTALL,
)
attr_re = re.compile(r'(\w+)="([\d.\-]+)"')

for m in cell_re.finditer(content):
    cid = m.group(1)
    attrs = dict(attr_re.findall(m.group(2)))
    try:
        x = float(attrs["x"])
        y = float(attrs["y"])
        w = float(attrs["width"])
        h = float(attrs["height"])
    except KeyError:
        continue
    vertices[cid] = (x, y, w, h)

print(f"parsed {len(vertices)} vertices")

# 2. For each edge, compute source/target centers and pick anchor sides.
def pick_anchors(src, tgt):
    sx, sy, sw, sh = src
    tx, ty, tw, th = tgt
    scx, scy = sx + sw / 2, sy + sh / 2
    tcx, tcy = tx + tw / 2, ty + th / 2

    dx = tcx - scx  # +ve: target right of source
    dy = tcy - scy  # +ve: target below source

    # If target horizontally overlaps source, force vertical routing.
    horiz_overlap = not (tx + tw < sx or sx + sw < tx)
    vert_overlap = not (ty + th < sy or sy + sh < ty)

    if horiz_overlap and not vert_overlap:
        # Vertical only
        if dy > 0:
            return (0.5, 1, 0.5, 0)  # exit bottom, enter top
        else:
            return (0.5, 0, 0.5, 1)  # exit top, enter bottom
    if vert_overlap and not horiz_overlap:
        # Horizontal only
        if dx > 0:
            return (1, 0.5, 0, 0.5)  # exit right, enter left
        else:
            return (0, 0.5, 1, 0.5)  # exit left, enter right
    # Diagonal — pick the dominant axis
    if abs(dy) >= abs(dx):
        if dy > 0:
            return (0.5, 1, 0.5, 0)
        else:
            return (0.5, 0, 0.5, 1)
    else:
        if dx > 0:
            return (1, 0.5, 0, 0.5)
        else:
            return (0, 0.5, 1, 0.5)


# 3. Rewrite each edge's style. Strip old exit*/entry* keys first so the
#    script is idempotent.
edge_re = re.compile(
    r'(<mxCell\s+id="[^"]+"\s+style=")([^"]*)("\s+edge="1"\s+parent="1"\s+source="([^"]+)"\s+target="([^"]+)">)',
    re.DOTALL,
)
strip_re = re.compile(r"(?:exit|entry)[XY]?=[^;]+;|(?:exit|entry)D[xy]=[^;]+;")

count = 0
def rewrite(m):
    global count
    pre, style, post, sid, tid = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    if sid not in vertices or tid not in vertices:
        return m.group(0)
    style = strip_re.sub("", style)
    ex, ey, nx, ny = pick_anchors(vertices[sid], vertices[tid])
    anchors = (
        f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;"
        f"entryX={nx};entryY={ny};entryDx=0;entryDy=0;"
    )
    count += 1
    return f"{pre}{anchors}{style}{post}"


new_content = edge_re.sub(rewrite, content)
PATH.write_text(new_content, encoding="utf-8")
print(f"rewrote {count} edges")
