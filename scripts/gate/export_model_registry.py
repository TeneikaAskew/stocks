#!/usr/bin/env python3
"""Export the model registry tables to docs/product/generated/model-registry.json.

Machine-owned (DOC_REGISTRY class A). Regenerate whenever
docs/product/07-MODEL-REGISTRY.md or docs/EXPERIMENT_REGISTRY.md changes:

    python3 scripts/gate/export_model_registry.py                     # write the JSON
    python3 scripts/gate/export_model_registry.py --check             # exit 1 if the committed JSON is stale
    python3 scripts/gate/export_model_registry.py --check --rev SHA   # the same, read from a commit (CI)
    python3 scripts/gate/export_model_registry.py --check --rev SHA --base SHA  # stale only if this PR did it

The refresh-canvas skill reads this file from main and merges it into the
"Stocks models diagram" canvas field by field. Nothing here is re-measured;
it is a parse of the markdown tables, with markdown links reduced to text
and issue/PR numbers extracted.

Provenance is `sources`: the git blob id of each source document, which is
the same on every commit that carries that content. --check compares it too,
so a JSON exported from different source text is stale even when the parsed
tables happen to match. Both documents are canonical inputs: if either is
missing at the rev being read, generation and --check fail naming the path,
so the JSON never carries a null source blob (CLAUDE.md §3.7).

A PR head contains main, so one registry edit that reaches main without its
JSON would fail every later PR. With --base, a stale head fails only when the
PR itself touches a source or the JSON, or when the base was fresh and the
head made it stale (a merge of a stale main it carries); otherwise the notice
names main and the check passes.
"""
from __future__ import annotations

import datetime
import html
import unicodedata
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = "docs/product/07-MODEL-REGISTRY.md"
EXPERIMENTS = "docs/EXPERIMENT_REGISTRY.md"
OUT = "docs/product/generated/model-registry.json"
SELF = "scripts/gate/export_model_registry.py"

LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
ISSUE = re.compile(r"#(\d+)\b")
CODE = re.compile(r"`([^`]+)`")
DOC_ID = re.compile(r"DOC-(\d+)")
RANGE_SEP = r"(?:…|\.\.\.?|[\u2010-\u2015\u2212]|→|->|\bto\b)"   # (round five: a figure dash or an arrow is a range too)
DOC_RANGE = re.compile(r"DOC-(\d+)\s*" + RANGE_SEP + r"\s*DOC-(\d+)")
EXP_ID = re.compile(r"\bE-(\d{2})\b")
EXP_RANGE = re.compile(r"\bE-(\d{2})\s*" + RANGE_SEP + r"\s*E-(\d{2})\b")

# Every model card reads these keys. A tier whose table has no column for one
# gets an explicit null: "the registry does not say", never a missing key.
CANONICAL = ("name", "type", "decision_produced", "code_paths", "status", "rec", "doc", "blocking_issues")
ALIASES = {"code_artifact": "code", "code_artifact_paths": "code_paths"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)


class Source:
    """Reads the registry documents from the working tree, or from one commit."""

    def __init__(self, rev: str | None = None):
        self.rev = rev

    def read(self, path: str) -> str | None:
        if self.rev is None:
            p = ROOT / path
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        r = git("show", f"{self.rev}:{path}")
        return r.stdout if r.returncode == 0 else None

    def require(self, path: str) -> str:
        """The document's text; a canonical source that is missing fails the run rather than exporting a null blob."""
        text = self.read(path)
        if text is None:
            where = f"at {self.rev}" if self.rev is not None else "in the working tree"
            raise SystemExit(f"{path} not found {where}; both registry sources must exist to export or check")
        return text

    def blob(self, path: str) -> str | None:
        if self.rev is None:
            r = git("hash-object", "--", path)
        else:
            r = git("rev-parse", f"{self.rev}:{path}")
        return r.stdout.strip() if r.returncode == 0 else None


# The tiers the registry is organized in (its `## ` sections holding model tables); each keeps
# at least one row, so a table deleted whole is refused rather than exported as an empty tier.
MODEL_TIERS = ("Deterministic and heuristic systems", "Learned models", "LLM nodes")


# Line endings GFM does not recognise: str.splitlines() would split on them and read a
# second row GFM renders as excess cells of the first (red-team round three)
ODD_BREAKS = re.compile("[\u2028\u2029\x0b\x0c\x1c\x1d\x1e\x85]")
UNICODE_DASH = re.compile("\\b(MODEL|DOC|E)[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")
INVISIBLE = re.compile("[\u200b-\u200f\u00ad\u2060-\u2064\ufeff\u034f\u180e\u061c\u202a-\u202e\u2066-\u2069]"
                       "|[\ufe00-\ufe0f](?=[A-Za-z0-9-])|(?<=[A-Za-z0-9-])[\ufe00-\ufe0f]")   # a variation selector inside a word
# GFM's whitespace is ASCII: a no-break or em space is content, so a line of them is a row and one
# before a pipe is a cell (red-team round five)
ODD_SPACE = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")
# letters outside ASCII that read as an ID's letters on the page (round four: `МODEL-GAMMA-001` with a Cyrillic М)
CONFUSABLE = str.maketrans("АВСЕНКМОРТХаеорсхＭＯＤＥＬＣ", "ABCEHKMOPTXaeopcxMODELC")


def lookalike_id(text: str) -> str | None:
    """A token that spells MODEL-, DOC- or E-nn with a letter or dash that is not the ASCII one."""
    for token in re.findall(r"[^\s|()`*_,;]+", text):
        if token.isascii():
            continue
        folded = unicodedata.normalize("NFKC", token.translate(CONFUSABLE))
        if (m := re.match(r"(?i)(?:MODEL|DOC|E)-\w+", folded)) and token[:m.end()] != m.group(0):
            return token   # the ID itself changed under folding; a `…` after it is punctuation
        # round five: a Greek, Lisu or Cherokee letter folds to nothing, so judge the shape: an ID-shaped
        # token with a non-ASCII letter where an ASCII one would be
        shape = "".join("X" if not c.isascii() and c.isalpha() else c for c in token)
        if shape != token and re.fullmatch(r"(?:X?[A-Z]*X?)+-[A-Z0-9X]+(?:-[A-Z0-9X]+)*|X-\d{2}", shape) and re.match(r"[A-Z]*X|X", shape):
            return token
    return None


def split_lines(text: str) -> list[str]:
    """Lines as GFM reads them: LF, CRLF or CR, nothing else."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def clean(cell: str) -> str:
    # An HTML comment is audit markup, not content: canvases.yml maps cells straight
    # onto card text, so a hidden directive would be published on a card.
    cell = re.sub(r"<!--.*?-->", "", cell, flags=re.S)
    cell = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", cell)   # an image renders its alt text (round six)
    cell = LINK.sub(r"\1", cell)
    cell = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", cell)   # a reference link renders its text
    cell = re.sub(r"<((?:https?|mailto):[^>\s]+)>", r"\1", cell)   # an autolink renders its URL
    if re.search(r"\[[^\]]*\[", re.sub(r"<!\[CDATA\[.*?\]\]>", "", cell)):
        raise SystemExit(f"{REGISTRY}: a cell holds a nested link ({cell.strip()[:40]!r}); write links one at a time")
    cell = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"\1", cell).replace("~~", "")   # (round seven: `sigma**2` is not emphasis)
    cell = re.sub(r"(?<![\w`*_])[*_]{1,3}(?=[^\s*_])|(?<=[^\s*_])[*_]{1,3}(?![\w`*_])", "", cell)   # emphasis renders its word; `sigma**2` keeps its stars
    # red-team round three: `E\-99`, `E&#45;99` and `<s>x</s>` render as the plain text; inside a
    # code span a backslash, an entity and a tag are literal, so only the prose between spans changes
    out, at = [], 0
    for span in re.finditer(r"(`+)(?:(?!\1)[\s\S])*?\1", cell):   # a span opens and closes with the same run of backticks
        out += [prose(cell[at:span.start()]), span.group(0)]
        at = span.end()
    out.append(prose(cell[at:]))
    return re.sub(r"\s+", " ", "".join(out)).strip()


# GFM's inline HTML: an open tag with well-formed attributes, a closing tag, a comment, a processing
# instruction, a declaration or CDATA. `<MODEL-X =x>` is none of these and renders as text (round five)
INLINE_HTML = re.compile(
    r"""<[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z_:][\w.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)*\s*/?>"""
    r"|</[A-Za-z][A-Za-z0-9-]*\s*>|<\?.*?\?>|<![A-Za-z][^>]*>|<!\[CDATA\[.*?\]\]>")


def prose(text: str) -> str:
    text = INLINE_HTML.sub("", html.unescape(text))
    return re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text)


def split_row(line: str) -> list[str]:
    """Cells of a GFM row: the leading and trailing pipes are optional (red-team, this PR: a row
    written without its leading pipe renders, and used to end the table here)."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [p.replace("\\|", "|").strip() for p in re.split(r"(?<!\\)\|", text)]


def expand_ids(cell: str, id_re: re.Pattern, range_re: re.Pattern, fmt: str,
               drop_parentheticals: bool = False) -> list[str]:
    """Every ID a cell names: ranges (`DOC-01…DOC-05`) expanded, lists split, and,
    where asked, parenthetical decorations such as `(#1118)` dropped."""
    text = clean(cell)
    ids: list[str] = []
    for a, b in range_re.findall(text):
        if int(a) > int(b):
            # red-team round two: `E-99…E-01` expanded to nothing and cited no experiment at all
            raise SystemExit(f"{REGISTRY}: the range {fmt.format(int(a))}…{fmt.format(int(b))} runs backwards and names nothing")
        ids += [fmt.format(n) for n in range(int(a), int(b) + 1)]
    text = range_re.sub(" ", text)
    if drop_parentheticals:
        text = re.sub(r"\([^)]*\)", " ", text)
    ids += [fmt.format(int(n)) for n in id_re.findall(text)]
    return list(dict.fromkeys(ids))


def doc_ids(cell: str) -> list[str]:
    return expand_ids(cell, DOC_ID, DOC_RANGE, "DOC-{:02d}", drop_parentheticals=True)


HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt"
    "|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu"
    "|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1)[\s\S])*?\1")


def html_block(line: str, can_interrupt: bool) -> tuple[str, str] | None:
    """(kind, end-pattern) when `line` opens one of GFM's seven HTML block kinds (red-team round
    four: `<pre>`, `<?`, `<![CDATA[` and `<!-->` each hid or exposed rows differently from the page)."""
    head = line[:3].lstrip() if line.startswith("   ") else line.lstrip(" ")
    if not line[: len(line) - len(line.lstrip(" "))].__len__() <= 3:
        return None
    t = line.lstrip(" ")
    if re.match(r"(?i)<(pre|script|style|textarea)(\s|>|$)", t):
        return "1", r"(?i)</(pre|script|style|textarea)>"
    if t.startswith("<!--"):
        return "2", r"-->"
    if t.startswith("<?"):
        return "3", r"\?>"
    if re.match(r"<![A-Za-z]", t):
        return "4", r">"
    if t.startswith("<![CDATA["):
        return "5", r"\]\]>"
    if re.match(r"(?i)</?(" + HTML_BLOCK_TAGS + r")(\s|/?>|$)", t):
        return "6", ""
    if can_interrupt is False and re.match(r"^(<[a-zA-Z][a-zA-Z0-9-]*(\s+[^<>]*?)?\s*/?>|</[a-zA-Z][a-zA-Z0-9-]*\s*>)\s*$", t):
        return "7", ""
    return None


def rendered(text: str) -> str:
    """The document as it renders: HTML blocks, HTML comments, fenced and indented code removed,
    so a table retired inside any of them is not exported and published on a card. One pass in
    document order, as a Markdown parser reads it (red-team rounds two to four)."""
    out: list[str] = []
    fence: str | None = None
    block_end: str | None = None   # the end pattern of the open HTML block; "" ends at a blank line
    block_kind = ""
    in_code = False
    prev_blank, last_kept = True, ""
    for line in split_lines(text):
        if block_end is not None:
            if block_kind in ("6", "7") and re.search(r"(?i)<(table|tr|td|th)\b", line):
                # round six: a raw `<table>` renders as a table the exporter never reads
                raise SystemExit(f"{REGISTRY}: {line.strip()[:60]!r} is a raw HTML table the page renders; write tables in Markdown")
            if block_end == "" and not line.strip():
                block_end = None   # kinds 6 and 7 end at the blank line, which stays blank
            elif block_end and re.search(block_end, line):
                block_end = None   # kinds 1 to 5 end on the line carrying the closer, which is theirs
                out.append("")
                continue
            else:
                out.append("")
                continue
        if fence is not None:
            if re.match(r"^ {0,3}" + re.escape(fence) + fence[0] + r"*[ \t]*$", line):
                fence = None
            out.append("")   # (round seven: a fence between rows ends the table on the page)
            continue
        # a fence opens and closes only within three spaces of indentation; four columns (spaces or a
        # tab, expanded to its stop) after a blank line is an indented code block (rounds three, four)
        indented = line.expandtabs(4).startswith("    ")
        if in_code and (indented or not line.strip()):
            continue
        # (under a list item an indented block is the item's continuation, not code: kept, so a table
        # there is refused as nested rather than dropped)
        in_code = indented and prev_blank and not re.match(r"^\s*([-*+]|\d+[.)])\s", last_kept)
        was_blank, prev_blank = prev_blank, not line.strip()
        if in_code:
            continue
        if line.strip():
            last_kept = line
        if (opener := re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)) and not (opener.group(1)[0] == "`" and "`" in opener.group(2)):
            fence = opener.group(1)
            out.append("")
            continue
        if (kind := html_block(line, can_interrupt=not was_blank)) is not None:
            if re.match(r"(?i)^ {0,3}<h[1-6][\s>]", line):
                # round five: `<h3>Retired nodes</h3>` is a heading on the page the tier logic never sees
                raise SystemExit(f"{REGISTRY}: {line.strip()[:60]!r} is an HTML heading; headings are written as `## `")
            if re.search(r"(?i)<(table|tr|td|th)\b", line):
                # round six: a raw `<table>` renders as a table the exporter never reads
                raise SystemExit(f"{REGISTRY}: {line.strip()[:60]!r} is a raw HTML table the page renders; write tables in Markdown")
            block_kind, block_end = kind
            if block_end and re.search(block_end, line.lstrip(" ")[2:]):
                block_end = None   # opened and closed on one line: that line is the block (`<!-->` too)
            out.append("")
            continue
        # a comment closed on the line is audit markup; one holding a pipe would split the row for GFM
        prose = CODE_SPAN.sub(lambda m: "`" * len(m.group(0)), line)
        for m in re.finditer(r"<!--.*?-->", prose):
            if "|" in m.group(0) and "|" in prose:
                raise SystemExit(f"{REGISTRY}: a comment on a table row holds a pipe ({m.group(0)[:40]!r}); GFM splits the row at it")
        stripped = re.sub(r"<!--.*?-->", "", prose)
        if "<!--" in stripped and "|" not in stripped:
            # round four: an unclosed `<!--` in prose is text for GFM, never a comment that hides what follows
            raise SystemExit(f"{REGISTRY}: {line.strip()[:60]!r} opens a `<!--` it does not close; GFM renders it as text, so close or remove it")
        keep = re.sub(r"<!--.*?-->", "", CODE_SPAN.sub(lambda m: m.group(0), line)) if "<!--" not in prose else _strip_comments(line)
        out.append(keep)
    return "\n".join(out)


def _strip_comments(line: str) -> str:
    """Complete comments removed from the prose of a line, code spans kept as written."""
    out, at = [], 0
    for span in CODE_SPAN.finditer(line):
        out += [re.sub(r"<!--.*?-->", "", line[at:span.start()]), span.group(0)]
        at = span.end()
    out.append(re.sub(r"<!--.*?-->", "", line[at:]))
    return "".join(out)


def last_reviewed(text: str) -> str:
    """The visible `**Last reviewed:**` stamp, a calendar date or `unknown`: read from the
    rendered text so a commented-out earlier stamp cannot supply it (stocks#1205 r4120381528)."""
    m = re.search(r"(?m)^\*\*Last reviewed:\*\*[ \t]*(\S+)", rendered(text).split("\n## ", 1)[0])   # the document's stamp, on its own line, not a section's or a cell's (round five)
    value = m.group(1) if m else None
    if value != "unknown":
        try:
            datetime.date.fromisoformat(value or "")
        except ValueError:
            raise SystemExit(f"{REGISTRY}: the visible **Last reviewed:** stamp reads {value!r}; it is a YYYY-MM-DD date or `unknown`")
    return value


REQUIRED_KEYS = {
    # the fields canvases.yml routes onto a card: a dropped column would leave every record
    # without the path the refresh writes (stocks#1205 r4120381495)
    "finding": ("id", "doc", "kind", "sev", "models"),
    "disposition": ("id", "disposition", "why"),
    "traceability": ("model", "experiments", "primary_code", "deep_doc", "recorded_verdict"),
}


def tables_with_headings(text: str):
    """Yield (heading_path, header_cells, rows) for every markdown table that renders."""
    heading: list[str] = []
    # stocks#1205 r4121216904: GFM renders a row indented by up to three spaces as part of
    # the table, so such a row is a row here too, not the end of the table
    raw_lines = [ln.expandtabs(4) for ln in split_lines(rendered(text))]   # a tab is its column stop (round four)
    lines = [re.sub(r"^ {1,3}(?=[|#])", "", ln).rstrip() for ln in raw_lines]   # trailing blanks are not content
    consumed: set[int] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*(>|[-*+]\s|\d{1,9}[.)]\s)\s*#{1,6}\s", line):
            # round four: a heading inside a blockquote or list item renders there, and the table under
            # it would be keyed to the tier above
            raise SystemExit(f"{REGISTRY}: {line.strip()[:60]!r} is a heading inside a blockquote or list item; headings sit at the top level")
        hm = re.match(r"^(#{1,6})(?:\s+(.*?))?\s*(?:(?<=\s)#+)?\s*$", line)
        if hm:
            level = len(hm.group(1))
            heading = heading[: level - 1] + [clean(hm.group(2) or "")]
            i += 1
            continue
        # a setext heading: text underlined with === or --- (round four; the ledger reader knew them already)
        if line.strip() and "|" not in line and i + 1 < len(lines) and re.match(r"^ {0,3}(=+|-+)\s*$", lines[i + 1]) \
                and (i == 0 or not lines[i - 1].strip()) and not re.match(r"^ {0,3}([-*+]\s|\d+[.)]\s|>|#|```|~~~|    )", line):
            level = 1 if lines[i + 1].strip().startswith("=") else 2
            heading = heading[: level - 1] + [clean(line.strip())]
            i += 2
            continue
        # stocks#1205 r4121777339: every delimiter cell carries a hyphen, or GFM renders no table
        if "|" in line and i + 1 < len(lines) and DELIMITER.match(lines[i + 1]) and "-" in lines[i + 1]:
            # red-team round three: a blockquote, list item or paragraph directly above swallows the header
            # row into itself (lazy continuation), so GFM renders no table at all
            if i and lines[i - 1].strip() and not re.match(r"^#{1,6}(\s|$)", lines[i - 1]):
                raise SystemExit(f"{REGISTRY}: the table at {line.strip()[:60]!r} follows {lines[i - 1].strip()[:40]!r} without a blank "
                                 "line, so GFM renders it as part of that block, not as a table")
            header = [clean(c) for c in split_row(line)]
            if len(split_row(lines[i + 1])) != len(header):
                # red-team, this PR: GFM renders no table when the delimiter row's width differs
                raise SystemExit(f"{REGISTRY}: the table under '{' / '.join(heading)}' has a header of {len(header)} cells and a "
                                 f"delimiter row of {len(split_row(lines[i + 1]))}; GFM renders no table, so nothing here exports")
            rows = []
            consumed.update((i, i + 1))
            i += 2
            # a row is any following non-blank line up to a heading, fence, list item or blockquote: GFM
            # does not need the leading pipe (red-team, this PR), and a line without any pipe renders
            # as a one-cell row of the table, not as prose (red-team round two)
            # (a heading needs a space after its hashes and a fence sits within three spaces: `#| x |` is a row)
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}(\s|$)|```|~~~)", lines[i]) and not BLOCK_START.match(lines[i]):
                if "|" not in lines[i]:
                    raise SystemExit(f"{REGISTRY}: {lines[i].strip()!r} directly under the table in '{' / '.join(heading)}' has no "
                                     "pipe; GFM renders it as a row of that table. Put a blank line before it or make it a row")
                if raw_lines[i].startswith("    "):
                    raise SystemExit(f"{REGISTRY}: {lines[i].strip()[:60]!r} under the table in '{' / '.join(heading)}' is indented "
                                     "four spaces; GFM ends the table there and renders it as code")
                if "<!--" in lines[i]:
                    raise SystemExit(f"{REGISTRY}: a row under '{' / '.join(heading)}' carries an unclosed `<!--`; GFM renders it as "
                                     "text, so close the comment on the same line or remove it")
                rows.append(split_row(lines[i]))
                consumed.add(i)
                i += 1
            yield list(heading), header, rows
            continue
        i += 1
    for j in range(1, len(lines)):
        # red-team round two: a table inside a blockquote, a list item or an indented block renders
        # (cmark-gfm) but no shape above reads it, so its rows would be published and never exported
        if j not in consumed and (bare := NESTING.sub("", lines[j])) and DELIMITER.match(bare) and "-" in bare \
                and "|" in NESTING.sub("", lines[j - 1]):
            raise SystemExit(f"{REGISTRY}: the table at {lines[j - 1].strip()!r} sits inside a blockquote, list item or indented "
                             "block; it renders but is not exported. Move it to the top level")


BLOCK_START = re.compile(r"^\s*(>|[-*+]\s|\d{1,9}[.)]\s)")        # another block begins: the table ends (a marker has at most nine digits: round seven)
NESTING = re.compile(r"^(\s|>|[-*+]\s|\d{1,9}[.)]\s)*")             # blockquote and list prefixes
DELIMITER = re.compile(r"^\|?(\s*:?-+:?\s*\|)*\s*:?-+:?\s*\|?$")


def header_keys(header: list[str]) -> list[str]:
    return [re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_") or "col" for h in header]


def duplicate_keys(header: list[str]) -> list[str]:
    """Header cells that normalize to a key another cell already took: the later cell would
    silently overwrite the earlier field (stocks#1205 r4119966296)."""
    keys = header_keys(header)
    return sorted({k for k in keys if keys.count(k) > 1})


# Keys the exporter derives from a row: a header cell normalizing to one would be overwritten
# by, or overwrite, the derived value, and the card would read the wrong field (red-team round two)
DERIVED_KEYS = {"code_paths", "code_artifact_paths", "primary_code_paths", "issue_numbers", "unsourced", "tier", "label", "models_note"}


def derived_collisions(header: list[str], scheduler: bool) -> list[str]:
    taken = DERIVED_KEYS | ({"models"} if scheduler else set())
    return sorted(k for k in header_keys(header) if k in taken)


def row_to_record(header: list[str], raw: list[str]) -> dict:
    rec: dict = {}
    for key, cell in zip(header_keys(header), raw):
        rec[key] = clean(cell)
        if key in ("code", "code_artifact", "primary_code"):
            rec[key + "_paths"] = CODE.findall(cell)
        if key in ("blocking_issues", "evidence", "recorded_verdict", "note"):
            # stocks#1205 r4121413706: Evidence and Blocking issues both carry references; union them
            rec["issue_numbers"] = sorted(set(rec.get("issue_numbers", [])) | {int(n) for n in ISSUE.findall(cell)})
    return rec


def canonical(rec: dict) -> dict:
    for src, dst in ALIASES.items():
        if src in rec and dst not in rec:
            rec[dst] = rec[src]
    for key in CANONICAL:
        rec.setdefault(key, None)
    return rec


def experiment_ids(text: str) -> list[str]:
    """IDs from experiment headings only: prose such as "Next free ID is E-36" is not an experiment."""
    ids: set[str] = set()
    leads: list[str] = []   # the ID a heading starts with: its own entry, not a mention or a session's range
    lines = split_lines(rendered(text))   # a heading inside a fence is an example, not an entry (r4120660287)
    for n, line in enumerate(lines):
        # red-team round two: a setext heading (text underlined with === or ---) is a heading too
        if n + 1 < len(lines) and re.match(r"^ {0,3}(=+|-+)\s*$", lines[n + 1]) and line.strip() \
                and (n == 0 or not lines[n - 1].strip()) and not re.match(r"^ {0,3}([-*+]\s|\d+[.)]\s|>|#|\||```|~~~|    )", line):
            line = "# " + line.strip()
        if re.match(r"^ {0,3}#{1,6}\s", line):   # stocks#1205 r4121602828: up to three spaces still render a heading
            if (lead := re.match(r"^ {0,3}#{1,6}\s+(" + EXP_ID.pattern + r")\b", line)):
                leads.append(lead.group(1))
                ids.update(expand_ids(lead.group(0), EXP_ID, EXP_RANGE, "E-{:02d}"))
            else:
                # a session heading lists its experiments in parentheses; a heading that merely mentions
                # one in prose defines nothing (red-team, this PR)
                for group in re.findall(r"\(([^)]*)\)", line):
                    # (round six: "(compare E-07 next quarter)" is a mention; a session list holds IDs, ranges and P-items only)
                    if re.fullmatch(r"\s*(?:E-\d{2}(?:\s*" + RANGE_SEP + r"\s*E-\d{2})?|P\d(?:\.\d+)?)(?:[\s,+]+(?:E-\d{2}(?:\s*" + RANGE_SEP + r"\s*E-\d{2})?|P\d(?:\.\d+)?))*[\s,+]*", group):
                        ids.update(expand_ids(group, EXP_ID, EXP_RANGE, "E-{:02d}"))
    if dup := sorted({i for i in leads if leads.count(i) > 1}):
        # stocks#1205 r4121777347: two entries for one ID are two records a citation cannot tell apart
        raise SystemExit(f"experiment {dup[0]} is defined by more than one heading in the ledger; one entry per ID")
    return sorted(ids)


LLM_GROUP = re.compile(r"\bLLM nodes\b")
COMPLEMENT = re.compile(r"\b(except|excluding|but not|other than|without|formerly|no longer|now none|previously|used to)\b", re.I)
LOWER_ID = re.compile(r"\b(?=[a-zA-Z0-9-]*[a-z])[mM][oO][dD][eE][lL](?:-[a-zA-Z0-9]+)*-\d+\b")   # `model-gamma-001`: an ID in the wrong case, not prose


def resolve_scheduler_models(schedulers: list[dict], models: dict) -> None:
    """Fill `models` for a scheduler whose Serves cell names no MODEL-* id.

    Two forms are expanded, both deterministic: a phrase naming the LLM node
    group ("all 14 LLM nodes", "the LLM nodes' delivery half") becomes every
    id in the `LLM nodes` tier, and a row that runs another row's Job (the
    Sunday refresh of a job whose weekday row lists its models, whether or not
    it says "the same job") inherits the ids those rows name literally. Any
    other prose is not guessed at: `models` stays empty and `models_note`
    carries the Serves text, so the canvas shows the gap instead of hiding it.
    """
    llm_ids = sorted(mid for mid, rec in models.items() if rec.get("tier") == "LLM nodes")
    by_job: dict[str, set[str]] = {}
    for rec in schedulers:
        if rec["models"]:
            by_job.setdefault(rec.get("job", ""), set()).update(rec["models"])
    for rec in schedulers:
        if rec["models"]:
            continue
        serves = rec.get("serves", "")
        if re.search(r"\b(no|not|never|none)\b", serves, re.I) and (LLM_GROUP.search(serves) or "same job" in serves.lower()):
            # red-team round three: "not the LLM nodes any more" expanded to the LLM nodes
            raise SystemExit(f"{REGISTRY}: scheduler {rec.get('scheduler', '')} Serves reads {serves!r}, a negation the exporter "
                             "does not resolve; name the models or say what it serves")
        if LLM_GROUP.search(serves):
            rec["models"] = llm_ids
        elif "same job" in serves.lower() and by_job.get(rec.get("job", "")):
            rec["models"] = sorted(by_job[rec["job"]])
        else:
            rec["models_note"] = f"no registered model named in Serves: {serves}"


def build(src: Source) -> dict:
    text = src.require(REGISTRY)
    etext = src.require(EXPERIMENTS)
    for path, doc in ((REGISTRY, text), (EXPERIMENTS, etext)):
        if m := ODD_BREAKS.search(doc):
            raise SystemExit(f"{path}: carries U+{ord(m.group(0)):04X}, which is not a line ending GFM recognises; remove it")
        if m := INVISIBLE.search(html.unescape(doc)):   # `&#8203;` renders as the character (round five)
            raise SystemExit(f"{path}: carries an invisible character (U+{ord(m.group(0)):04X}); remove it")
        if m := ODD_SPACE.search(html.unescape(doc)):
            raise SystemExit(f"{path}: carries U+{ord(m.group(0)):04X}, a space GFM reads as content; use an ASCII space")
        if m := UNICODE_DASH.search(html.unescape(doc)):   # an entity renders as the character (round four)
            raise SystemExit(f"{path}: {m.group(0)!r} uses a look-alike dash; IDs are written with the ASCII hyphen")
        if token := lookalike_id(html.unescape(doc)):
            raise SystemExit(f"{path}: {token!r} spells an ID with a look-alike letter; IDs are ASCII")
    out: dict = {
        "generated_from": [REGISTRY, EXPERIMENTS],
        # The exporter is a source too: a changed exporter is a changed output, so a base
        # that changed it without regenerating reads stale rather than fresh.
        "sources": {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS, SELF)},
        "registry_last_reviewed": last_reviewed(text),
        "models": {},
        "experiment_traceability": {},
        "findings": [],
        "dispositions": {},
        "schedulers": [],
        "excluded_schedulers": [],
        "tables": [],
    }
    grouped: dict = {}
    unrouted: list[str] = []   # MODEL-/DOC- rows no table shape claimed: a malformed registry
    malformed: list[str] = []  # rows narrower or wider than their header, duplicate model IDs
    for heading, header, rows in tables_with_headings(text):
        h0 = header[0].lower() if header else ""
        section = " / ".join(heading)
        out["tables"].append({"section": section, "columns": header, "rows": len(rows)})
        for raw in rows:
            if not raw:
                continue
            first = clean(raw[0])
            # Width is checked on the rows that route (models, findings, dispositions,
            # schedulers): a prose table elsewhere in the document is not a record.
            routable = first.startswith(("MODEL-", "DOC-")) or h0 == "scheduler"
            if (LOWER_ID.match(first) or re.match(r"(?i)doc-\d", first)) and not first.startswith(("MODEL-", "DOC-")):
                # red-team round two: `model-gamma-001` neither routed nor failed; it vanished as prose
                malformed.append(f"{first!r} under '{section}' is a lower-case ID; IDs are upper-case MODEL-/DOC-")
                continue
            if routable and any(re.search(r"(?<!~)~(?!~)\S.*?\S~|~~", cell) or re.search(r"(?i)<(s|del|strike)\b", cell) for cell in raw):
                # red-team round two: `~~MODEL-X~~` renders struck through and exported as a live card
                malformed.append(f"{first} under '{section}' carries struck-through text; delete the row or restore it")
                continue
            if first.startswith("MODEL-") and h0 == "id" and "status" not in header_keys(header):
                # red-team round three: a renamed Status column exported every card's status as null
                malformed.append(f"the model table under '{section}' has no Status column; the cards read it")
                continue
            if routable and (taken := derived_collisions(header, h0 == "scheduler" and any(h.strip().lower() == "serves" for h in header))):
                malformed.append(f"table under '{section}' has a column keyed {taken[0]}, a field the exporter derives")
                continue
            # stocks#1205 r4121777330: a row in a model or concern table whose ID is not shaped
            # like the table's is a typo, not prose; it would vanish from the cards
            record_table = (h0 in ("id", "model") and any(k in " ".join(header).lower() for k in ("decision", "claim", "concern", "disposition", "experiments"))) \
                or (h0 == "id" and any(clean(r[0]).startswith(("MODEL-", "DOC-")) for r in rows if r))   # the LLM tier too (red-team, this PR)
            if first.startswith("MODEL-") and not re.fullmatch(r"MODEL-[A-Z0-9]+(-[A-Z0-9]+)*", first):
                malformed.append(f"{first!r} under '{section}' is not a bare model ID; the cards are keyed by the exact ID")
                continue
            if record_table and not routable:
                malformed.append(f"row {first!r} under '{section}' sits in a record table but is not a MODEL- or DOC- ID")
                continue
            if routable and len(raw) != len(header):
                malformed.append(f"{first} under '{section}' has {len(raw)} cell(s), header has {len(header)}")
                continue
            if routable and (dup := duplicate_keys(header)):
                malformed.append(f"table under '{section}' has two columns keyed {dup[0]}; one cell would overwrite the other")
                continue
            rec = row_to_record(header, raw)
            kind = ("traceability" if first.startswith("MODEL-") and h0 == "model"
                    else "finding" if first.startswith("DOC-") and ("concern" in " ".join(header).lower() or "claim" in " ".join(header).lower())
                    else "disposition" if first.startswith("DOC-") and "disposition" in " ".join(header).lower() else None)
            if kind and (missing := [k for k in REQUIRED_KEYS[kind] if k not in header_keys(header)]):
                malformed.append(f"the {kind} table under '{section}' lacks the {', '.join(missing)} column(s) the cards route")
                continue
            if first.startswith("MODEL-") and h0 == "id":
                if first in out["models"]:
                    malformed.append(f"{first} appears twice (second under '{section}')")
                    continue
                rec["tier"] = heading[1] if len(heading) > 1 else (heading[0] if heading else "")   # the `## ` tier, not a `### ` subsection
                out["models"][first] = canonical(rec)
            elif first.startswith("MODEL-") and h0 == "model":
                if first in out["experiment_traceability"]:
                    malformed.append(f"{first} has two experiment-traceability rows (second under '{section}')")
                    continue
                out["experiment_traceability"][first] = rec
            elif first.startswith("DOC-") and h0 == "id" and "concern" in " ".join(header).lower() or (
                first.startswith("DOC-") and "claim" in " ".join(header).lower()
            ):
                ids = doc_ids(raw[0])
                if len(ids) != 1:
                    # stocks#1205 r4120913740: a cell naming two concerns is two rows, not one
                    # card that drops the second; only disposition rows group findings
                    malformed.append(f"finding row {first!r} under '{section}' names {len(ids)} IDs; one finding per row")
                    continue
                rec["id"] = ids[0]
                rec["label"] = first
                out["findings"].append(rec)
            elif first.startswith("DOC-") and "disposition" in " ".join(header).lower():
                ids = doc_ids(raw[0])
                rec["label"] = first
                # A row naming one finding wins over a row that names it in a group.
                if len(ids) == 1 and ids[0] in out["dispositions"]:
                    # stocks#1205 r4119966278: two verdicts for one finding is a conflict, not a
                    # fallback; only a grouped row yields to a specific one
                    malformed.append(f"{ids[0]} has two disposition rows (second under '{section}')")
                    continue
                if len(ids) > 1 and (shared := sorted(set(ids) & set(grouped))):
                    # stocks#1205 r4120381475: two grouped rows naming one finding is the same conflict
                    malformed.append(f"{shared[0]} is named by two grouped disposition rows (second under '{section}')")
                    continue
                target = out["dispositions"] if len(ids) == 1 else grouped
                for fid in ids:
                    target.setdefault(fid, rec)
            elif h0 == "scheduler" and any(h.strip().lower() == "serves" for h in header):
                # From the Serves column itself, not the last cell: a column added after it
                # would otherwise silently empty every scheduler's model list.
                serves = next(cell for h, cell in zip(header, raw) if h.strip().lower() == "serves")   # not `Observes` (round four)
                rec["models"] = sorted(set(re.findall(r"MODEL-[A-Z0-9-]+", clean(serves))))
                if rec["models"] and (LLM_GROUP.search(clean(serves)) or COMPLEMENT.search(clean(serves))):
                    # round four: "all LLM nodes except MODEL-X" and "formerly MODEL-X, now none" exported MODEL-X
                    malformed.append(f"scheduler {first} Serves reads {clean(serves)[:60]!r}; name the models it serves, without exceptions or history")
                    continue
                if lower := LOWER_ID.findall(clean(serves)):
                    malformed.append(f"scheduler {first} Serves names {lower[0]} in lower case; IDs are upper-case")
                    continue
                out["schedulers"].append(rec)
            elif h0 == "scheduler":
                out["excluded_schedulers"].append(rec)
            elif first.startswith(("MODEL-", "DOC-")):
                unrouted.append(f"{first} under '{section}' (columns: {', '.join(header)})")
    for fid, rec in grouped.items():
        out["dispositions"].setdefault(fid, rec)
    # red-team round two: `x` and x are one scheduler; compare the name, not its markup
    names = [re.sub(r"^[*_]+|[*_]+$", "", clean(str(rec.get("scheduler", ""))).replace("`", "")) for rec in out["schedulers"]]
    for dup in sorted({n for n in names if n and names.count(n) > 1}):
        malformed.append(f"scheduler {dup} appears twice; one row per scheduler")
    seen_findings: set[str] = set()
    for rec in out["findings"]:
        # stocks#1205 r4119634446: the Concerns board is keyed by id, so two rows with one
        # ID would leave one finding overwritten on refresh while the ID-set check passed.
        if rec["id"] in seen_findings:
            malformed.append(f"finding {rec['id']} appears twice")
        seen_findings.add(rec["id"])
    ledger = set(experiment_ids(etext))
    for mid, rec in out["experiment_traceability"].items():
        # stocks#1205 r4119634454: a misspelled E-nn in a traceability row would let a card
        # claim evidence from an experiment the ledger never recorded.
        cited = set(expand_ids(clean(" ".join(str(v) for v in rec.values())), EXP_ID, EXP_RANGE, "E-{:02d}"))
        # stocks#1205 r4121888814: `E-3S` cites nothing and would be published verbatim
        mentioned = clean(" ".join(str(v) for v in rec.values()))
        if bad := sorted({t for t in re.findall(r"\bE-\w+", mentioned) if not re.fullmatch(r"E-\d{2}|E-(nn|NN|xx|XX)", t)}):
            malformed.append(f"{mid} traceability cites {', '.join(bad)}, not shaped E-NN (the placeholder `E-nn` is prose)")
        unknown_exp = sorted(cited - ledger)
        if unknown_exp:
            malformed.append(f"{mid} traceability cites experiment(s) not in the ledger: {', '.join(unknown_exp)}")
    if malformed:
        raise SystemExit(f"{REGISTRY}: {len(malformed)} malformed row(s): {'; '.join(malformed[:3])}. "
                         "A row has exactly its header's cells and a model ID names one row; fix the table "
                         "rather than exporting a shifted or overwritten record")
    finding_ids, disposition_ids = {f["id"] for f in out["findings"]}, set(out["dispositions"])
    if not finding_ids:
        # stocks#1205 r4120166753: two empty sets are equal, so a registry that lost both
        # concern tables would otherwise export an empty Concerns board as current
        raise SystemExit(f"{REGISTRY}: no finding rows parsed; the Findings and Disposition tables are part of the "
                         "registry, so their absence is a deleted table, not an empty board")
    if finding_ids != disposition_ids:
        raise SystemExit(f"{REGISTRY}: findings and dispositions name different IDs; without a disposition: "
                         f"{', '.join(sorted(finding_ids - disposition_ids)) or 'none'}; without a finding: "
                         f"{', '.join(sorted(disposition_ids - finding_ids)) or 'none'}. Every finding carries its verdict")
    tiers = {m["tier"] for m in out["models"].values()}
    missing_tiers = [t for t in MODEL_TIERS if t not in tiers]
    if missing_tiers:
        # Every tier the registry is organized in still carries models: a deleted table
        # would otherwise drop every card in it and --check would call the result current.
        raise SystemExit(f"{REGISTRY}: no model rows under {', '.join(missing_tiers)}; the registry keeps a table "
                         "for each of its tiers, so a missing one is a deleted table, not an empty tier")
    if not out["schedulers"]:
        # stocks#1205 r4119634461: a deleted model-bearing scheduler table, or a renamed
        # Serves header, would otherwise route every row to excluded_schedulers and export
        # every card without a scheduled surface, and --check would call that current.
        raise SystemExit(f"{REGISTRY}: no scheduler row routes to a model; the scheduled-surfaces table starts with "
                         "a `Scheduler` column and carries a `Serves` column. The registry is malformed; fix it "
                         "rather than exporting it")
    unknown = sorted({m for sched in out["schedulers"] for m in sched["models"] if m not in out["models"]})
    if unknown:
        raise SystemExit(f"{REGISTRY}: scheduler Serves cells name model(s) not in the registry: {', '.join(unknown)}; "
                         "a misspelled ID would silently drop the model from its scheduled surface")
    if not out["experiment_traceability"]:
        # stocks#1205 r4120660295: no rows is a deleted table; every card would lose its experiments
        raise SystemExit(f"{REGISTRY}: no experiment-traceability rows parsed; the table is part of the registry, so its "
                         "absence is a deleted table, not an empty one")
    orphans = sorted(set(out["experiment_traceability"]) - set(out["models"]))
    if orphans:
        # canvases.yml looks experiment fields up under the model's ID, so a misspelled
        # traceability key drops that card's experiment data without any other symptom.
        raise SystemExit(f"{REGISTRY}: experiment traceability names model(s) not in the registry: "
                         f"{', '.join(orphans)}; fix the ID rather than exporting an orphan row")
    if unrouted or not out["models"]:
        # A renamed `ID` header or a dropped section would otherwise export a partial or
        # empty models object, --check would call it current, and the canvas would
        # silently lose its cards. Zero recognized rows is a malformed source, not data.
        raise SystemExit(f"{REGISTRY}: {len(unrouted)} MODEL-/DOC- row(s) sit in a table shape the exporter does not "
                         f"recognize ({'; '.join(unrouted[:3])}) and {len(out['models'])} model(s) parsed; a model table "
                         "starts with an `ID` column. The registry is malformed; fix it rather than exporting it")
    for rec in out["findings"]:
        # red-team, this PR: a Concerns card naming a model that does not exist (after the tier
        # checks, so a broken model table reports as itself)
        if named := [m for m in re.findall(r"MODEL-[A-Z0-9-]+", str(rec.get("models", ""))) if m not in out["models"]]:
            raise SystemExit(f"{REGISTRY}: finding {rec['id']} names model(s) not in the registry: {', '.join(named)}; fix the ID")
        if lower := LOWER_ID.findall(str(rec.get("models", ""))):
            raise SystemExit(f"{REGISTRY}: finding {rec['id']} names {lower[0]} in lower case; IDs are upper-case")
    resolve_scheduler_models(out["schedulers"], out["models"])
    out["experiment_ids"] = experiment_ids(etext)
    # stocks#1205 r4121888831: the refresh skill protects a repo-owned field only when its JSON
    # value is null; a model without a traceability row gets every field as null, not no entry
    out["traceability_rows"] = len(out["experiment_traceability"])
    for mid in out["models"]:
        out["experiment_traceability"].setdefault(mid, {"model": mid, "unsourced": True, **{k: None for k in REQUIRED_KEYS["traceability"] if k != "model"}})
    return out


def fresh_at(rev: str) -> bool:
    """Whether the JSON at `rev` was exported from the sources at `rev`: its recorded blob ids match theirs."""
    src = Source(rev)
    committed = src.read(OUT)
    if committed is None:
        return False
    return json.loads(committed).get("sources") == {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS, SELF)}


def touched_since(base: str, rev: str) -> list[str]:
    """The registry sources, the JSON and this exporter that `rev` changed since it forked
    from `base` (the PR's own edits): a changed exporter is a changed output."""
    r = git("diff", "--name-only", f"{base}...{rev}", "--", REGISTRY, EXPERIMENTS, OUT, SELF)
    if r.returncode != 0:
        raise SystemExit(r.stderr.strip() or f"git diff {base}...{rev} failed")
    return r.stdout.split()


def option(argv: list[str], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def main(argv: list[str]) -> int:
    rev = option(argv, "--rev")
    if "--rev" in argv and rev is None:
        print("--rev needs a commit")
        return 2
    base = option(argv, "--base")
    if "--base" in argv and (base is None or rev is None or "--check" not in argv):
        print("--base needs a commit, and --check --rev")
        return 2
    src = Source(rev)
    data = build(src)
    payload = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if "--check" in argv:
        committed = src.read(OUT)
        if committed is None:
            print(f"missing {OUT}; run export_model_registry.py")
            return 1
        if json.loads(committed) != json.loads(payload):
            if base is not None and not touched_since(base, rev) and not fresh_at(base):
                print(f"{OUT} is already stale on the base branch (main at {base[:12]}), not in this PR; "
                      f"whoever last edited {REGISTRY} or {EXPERIMENTS} on main should regenerate it there: "
                      "run export_model_registry.py and commit the JSON")
                return 0
            print(f"{OUT} is stale; run export_model_registry.py and commit")
            return 1
        print("model-registry.json is current")
        return 0
    if rev is not None:
        print("--rev is read-only; use it with --check")
        return 2
    out = ROOT / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT}: {len(data['models'])} models, "
          f"{data['traceability_rows']} traceability rows, {len(data['findings'])} findings, "
          f"{len(data['dispositions'])} dispositions, {len(data['schedulers'])} schedulers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
