---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1707]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Current-baseline initialization controls fail on a387654214aacadf68be5e503cf175fd8ff4af08ec056660679a341cbf474b92 and pass after exactly the eleven declared literal factories and consumer substitutions, preserving all 53 pattern values, types and flags and all 42 other initializer bytes. Reversing only those edits reconstructs that exact baseline hash without network or historical Git objects."
  - "Meaningful first/repeated-use, exhaustive-compile, malformed-literal, Unicode/bytes, native accepted/refused verdict, import-shadow and renderer audit-fence regressions pass; every original current-main test name, case, parameter, assertion and native gate/hook invocation remains unchanged. PSEUDO_FILE is constructed before the audit hook is installed."
  - "Paired complete native original-suite measurements on identical baseline/proposed suite bytes and resource conditions demonstrate a positive wall-clock improvement with honest CPU and Git-dispatch evidence; the complete proposed serial suite including new controls finishes below 285 seconds, the unchanged BASE suite below 600 seconds, and the actual current-head registry job completes all tests and the unchanged exporter within the unchanged six-minute timeout, without a timing retry or deadline increase."
  - "The implementation has its own ready approved-spec-bound plan and scoped FEAT-CICD-001 records, ordinary SHARED-01 committed-source identity under the current fixed verifier limits, unchanged foreign SITE bytes and registry blob/mode/type, matched main/head no-new audits, the existing mandatory prepush governance review seats, authenticated current-head CODE/security review, green required CI and resolved conversations before merge. All earlier failed capacity and review receipts remain recorded."
status: draft
supersedes: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-regex-startup.md
---

# Current-base registry startup optimization

## Problem and evidence

This is a proposed current-base successor for issue #1707, not an implementation or a waiver. The owner requested fixing the required registry check while completing EW retirement. The reader changes do not own the gate or its suite, so this work has its own FEAT-CICD-001 delivery.

At #1801 head `8cd5ddc76ecbdda41cec1f12cff2a9f3fd565bba`, hosted run43040828762/job130591843070 was cancelled after the unchanged six-minute deadline. The job began 2026-11-11 14:41:09 UTC and ended14:47:11. Its annotation says "The job has exceeded the maximum execution time of 6m0s". The native suite printed181passed in306.77seconds at14:47:09, but the required exporter was skipped. This is failed capacity evidence, not a passing registry check. The triggering actor is not evidence of a human cancellation.

Issue #1707 records the same capacity pressure on unchanged main:178tests took294.68,306.46 and328.62seconds in three hosted runs. Current #1800's normal new-head registry success does not repair this root cause or erase #1801's timeout.

Current design base is `87409f213f2bc910e23f92ba1fa82ea1fd378bfd`. Its `scripts/gate/spec_gate.py` is298472bytes, SHA256 `a387654214aacadf68be5e503cf175fd8ff4af08ec056660679a341cbf474b92`. There are53 module-level `re.compile` assignments. An AST comparison against the predecessor's `6f03ab14a7c858e741d9023f215a1bf24e0371c1` source found all53 initializer expressions unchanged. The full source differs, so the predecessor's exact291006-byte reversal hash cannot be silently reused or changed during its implementation.

One diagnostic native accepted CLI invocation measured0.215seconds,18Git subprocesses at0.109seconds cumulative, and regex compilation at0.052seconds. This is not an isolated measurement of the eleven proposed patterns, not a full-suite speedup and not acceptance evidence. The unchanged serial suite must establish the actual gain.

## Alternatives and chosen scope

Choose the predecessor's bounded eleven-pattern deferred construction design, with current-base proof. It avoids retaining mutable Git inputs or verdicts and preserves every native test invocation. Fresh Git-read batching was previously considered separately; it has different failure/freshness risks and is excluded. Fixture reuse/process reuse, parallel pytest, a compiled replacement harness, changed runners/dependencies, skipped checks and timeout increases are excluded.

The only runtime source is `scripts/gate/spec_gate.py`; meaningful tests are appended to `tests/scripts/test_spec_gate.py`. Implement only these zero-argument `functools.lru_cache(maxsize=1)` factories and the existing consumer substitutions:

| Existing binding | Factory | Consumer |
|---|---|---|
| MANIFEST | _manifest_pattern | chore_allows.search |
| PLACEHOLDERS | _placeholders_pattern | shell_statements.search |
| REQUIREMENT_LINE | _requirement_line_pattern | non_dependency_edit.match |
| NPM_RANGE | _npm_range_pattern | dependency_values.match |
| HTML_TAG | _html_tag_pattern | raw_html.match |
| DECLARATION | _declaration_pattern | raw_html.match |
| FILTERED_TAG | _filtered_tag_pattern | raw_html.match |
| LETTER | _letter_pattern | read_index.finditer |
| COMMENT | _comment_pattern | uncommented.sub |
| CLEAN_BYTES | _clean_bytes_pattern | document_refusal.search |
| PSEUDO_FILE | _pseudo_file_pattern | render_fence.fence.fullmatch |

Each factory returns the ordinary compiled immutable literal, preserving all original arguments, flags and byte/string types. There is no proxy, generic dispatcher, file cache, bytecode cache or module `__getattr__`. Repeated sequential use returns its single retained compiled object even after `re.purge()`. Consumer method, arguments, evaluation order and diagnostics remain unchanged. PSEUDO_FILE is materialized once at render_fence entry and captured by the existing closure, before audit-hook registration. Preserve all42 other initializer bytes and every unrelated function body. Existing import ownership and native module execution remain unchanged.

Removing these private eager globals is the predecessor's explicit compatibility choice. Re-inventory direct and reflective consumers at implementation time. An additional consumer or identity contract requires revising the proposal; do not add a compatibility shim silently. Current external source/audit consumers and their trust rules remain unchanged.

## Proof and acceptance

Retain the predecessor's independent53-pattern expected literal inventory and exact eleven initializer snippets below; they match the current baseline AST. Tests must not derive expected values from the proposed factory. Pin the current source hash above; a test-only reversal of precisely the eleven factories/substitutions must recreate the exact baseline source, available without network or historical Git objects in shallow CI. Run that ordinary uncompiled CLI for baseline accepted/refused controls. A later main change to the source must be reconciled explicitly before implementation/publication; do not silently relax the reversal assertion.

Carry forward the predecessor's three regression classes: initialization exactness, exhaustive compilation/identity/flags and native verdict preservation. Cover first and repeated use, malformed unvisited literals, changed inline/explicit flags, byte/string substitutions, eager default arguments, mutable cache keys, imported consumers and renderer-hook construction order. Preserve all181 current original test functions/cases and all native gate/hook invocations. AST preservation is an additional control, not a replacement for executing the unchanged suite. No original case is skipped, weakened, reordered for timing, or moved to a faster substitute harness.

Measure the same original complete suite with baseline and proposed source, identical suite bytes, ordinary Python/environment and no concurrent CPU tests. Record wall and child CPU times and Git process counts, including failed samples. Then run the complete proposed suite with added meaningful regressions. Keep the predecessor's below285second local suite and below600second BASE targets; the live registry job remains six minutes, already present on main. This proposal changes no timeout from five to six, and does not use the unimplemented ten-minute envelope. Hosted acceptance includes the exporter. Do not multiply a microbenchmark into a speed claim or rerun a timeout to select a favorable sample. Insufficient savings holds delivery and requires an explicit new design.

Validate unchanged neighboring source-snapshot, docs-audit, exporter and generated-document suites. Renderer limits stay60seconds/512MiB; source verification uses current main's5seconds/12582912bytes/20000entries. This spec does not alter any safety limit, command grammar, workflow, pin, hook, dependency, test-import ownership or policy.

## Delivery, ownership and review history

This draft authorizes no runtime implementation. After written approval and actual spec merge, create one new ready plan/implementation branch from that main, with normal initial PLANONLY Draft PR and PR binding before code. Never repoint an existing plan or stack on an unmerged candidate. Check ownership of scripts/gate/spec_gate.py and tests/scripts/test_spec_gate.py with other FEAT-CICD writers before edits. Coordinate SHARED-01/sidecar sequencing with the root; do not alter reader-owned rows.

Preserve the existing issue1707, historical batching/regex proposals, #1801's raw cancelled run and the three local reader review passes and later hosted receipts. Those reader reviews do not count as this new governance proposal's reviews, nor does their scoped extra-review allowance reset any lineage. Existing review cap and required concrete governance prepush seats apply; reconcile their actual budget before requesting judgment review. No review is commissioned by writing this draft.

Implementation-owned delivery files are its new plan, FEAT-CICD-001 catalog/traceability record, SHARED-01 implementation-source note retaining earlier accurate prose, and ordinary sidecar. Use actual committed source and trusted main policy, retain all foreign SITE bytes and historical markers, compare registry blob/mode/type to main, and run full-default matched audits. Fresh postmerge main identity and lawful source-note close-out remain separate. No deployment or product data freshness claim is made.

## Capacity and risks

Volume:53 existing pattern definitions,11 bounded single-entry factories, all181 current native tests plus meaningful new controls. Velocity: unchanged native gate/hook and provider/SQL invocation counts; no new network calls. Wall-clock: measured failing hosted suite306.77seconds; proposed total unknown until paired/full hosted measurements. Cost: no new jobs, schedules, dependencies or paid runner; ordinary CI resource use is measured, not promised.

The main risks are altered pattern semantics, compilation inside the audit hook, hidden reflective consumers and insufficient full-suite savings. The exact independent inventory, reversal hash, native negative controls, unchanged suite and actual hosted exporter completion are mandatory evidence. No product runtime, GCP, financial algorithm or EW reader source changes belong here.

## Appendix A baseline pattern values

Each row is `[name, pattern_type, compiled_flags, Python_repr_of_pattern_value]`. The last field is the exact Python repr of the pattern value (including str/bytes distinction), not a replacement regex source. Safe `ast.literal_eval` recovers the immutable value. These are baseline source-derived constants, not new implementation or test results.

```json
[
  [
    "FEAT_ROW",
    "str",
    40,
    "'^\\\\|\\\\s*\\\\[?(FEAT-[A-Z]+-\\\\d{3})\\\\b'"
  ],
  [
    "FEAT_IDS",
    "str",
    32,
    "'\\\\bFEAT-[A-Z]+-\\\\d{3}\\\\b'"
  ],
  [
    "BRANCH",
    "str",
    32,
    "'^(feature|fix)/(feat-[a-z]+-\\\\d{3})(-[a-z0-9]+)+$'"
  ],
  [
    "REQ_SHAPE",
    "str",
    32,
    "'^REQ-[A-Z]+-\\\\d{3}$'"
  ],
  [
    "REQ_DEFINITION",
    "str",
    32,
    "'\\\\*\\\\*(REQ-[A-Z]+-\\\\d{3}):\\\\*\\\\*'"
  ],
  [
    "CHECKBOX",
    "str",
    32,
    "'^\\\\s*(?:[-*+]|\\\\d{1,9}[.)])\\\\s+\\\\[([ xX])\\\\]\\\\s+(\\\\S(?:.*\\\\S)?)\\\\s*$'"
  ],
  [
    "HEADING",
    "str",
    32,
    "'^ {0,3}(#{1,6})\\\\s'"
  ],
  [
    "ISO_DATE",
    "str",
    32,
    "'^\\\\d{4}-\\\\d{2}-\\\\d{2}$'"
  ],
  [
    "PR_REF",
    "str",
    32,
    "'^#?(\\\\d+)$'"
  ],
  [
    "PR_MENTION",
    "str",
    32,
    "'#(\\\\d+)(?![\\\\w])'"
  ],
  [
    "MANIFEST",
    "str",
    32,
    "'(^|/)(package(-lock)?\\\\.json|requirements[^/]*\\\\.(txt|lock)|pyproject\\\\.toml|poetry\\\\.lock|uv\\\\.lock|yarn\\\\.lock|pnpm-lock\\\\.yaml|bun\\\\.lock)$'"
  ],
  [
    "OTHER_BRANCH",
    "str",
    32,
    "'^((docs|chore)/[a-z0-9]+(-[a-z0-9]+)*|bot/superpowers-[a-z0-9]+(-[a-z0-9]+)*)$'"
  ],
  [
    "PLACEHOLDERS",
    "str",
    32,
    "'__SUB__|__VAR__|__STEP__|\\\\x00'"
  ],
  [
    "DEPLOY_FILE",
    "str",
    32,
    "'^((gcp|platform)/deploy\\\\.sh|gcp/cloudbuild/[^/]+|cloudbuild[^/]*\\\\.ya?ml|Dockerfile[^/]*|\\\\.gcloudignore|\\\\.dockerignore)$'"
  ],
  [
    "DEFERRAL",
    "str",
    34,
    "'\\\\b(future[- ]work|follow[- ]?up|non[- ]?blocking|for now|deferred|later PR|next PR|separate PR|TODO|TBD|not (?:yet )?(?:run|done|implemented|verified|tested|complete|completed|finished|started|applied|merged|shipped)|unfinished|incomplete|untested|unverified|outstanding|pending|(?<!\\\\d )(?<!\\\\d)skipped|still open|to be done|postpone\\\\w*|parked|park it|out of scope|descope\\\\w*|tracked in|will be (?:addressed|done|fixed|added|run)|after (?:the )?merge|phase \\\\d|not in this PR|next (?:sprint|release|iteration)|to follow|later (?:change|release)|punt\\\\w*|follow[- ]?ups|defer\\\\w*|backlog|(?:future|another|subsequent|follow[- ]on) PR|partial(?:ly)?|in progress|WIP|not fully|future (?:version|release)|tracked separately|later (?:in a|on))\\\\b'"
  ],
  [
    "LICENSE_FILE",
    "str",
    32,
    "'^(LICENSE|LICENCE|COPYING)(-[A-Za-z0-9]+)*(\\\\.(md|txt|rst))?$'"
  ],
  [
    "NOT_PROSE",
    "str",
    34,
    "'\\\\.(py|pyc|pyw|sh|bash|zsh|ps1|bat|cmd|js|mjs|cjs|ts|tsx|jsx|html?|xhtml|svg|whl|egg|zip|tar|tgz|tar\\\\.gz|tar\\\\.xz|7z|rar|toml|cfg|ini|rb|pl|php|exe|dll|so|dylib|jar|class|wasm|ipynb)$'"
  ],
  [
    "TASK_HEADING",
    "str",
    40,
    "'^ {0,3}#{2,3}\\\\s+Task\\\\b.*$'"
  ],
  [
    "REQUIREMENT_LINE",
    "str",
    32,
    "'^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\\\\[[A-Za-z0-9._,\\\\s-]*\\\\])?\\\\s*(?:(?:===?|~=|!=|<=|>=|<|>)\\\\s*[A-Za-z0-9._*+!-]+(?:\\\\s*,\\\\s*(?:===?|~=|!=|<=|>=|<|>)\\\\s*[A-Za-z0-9._*+!-]+)*)?\\\\s*(?:;[^/@:]*)?|--hash=sha(?:256|384|512):[0-9a-fA-F]+)$'"
  ],
  [
    "NPM_RANGE",
    "str",
    32,
    "'^(?:(?:\\\\^|~|>=?|<=?|=)?\\\\d[\\\\w.+-]*(?:\\\\s*(?:\\\\|\\\\||-|\\\\s)\\\\s*(?:\\\\^|~|>=?|<=?|=)?\\\\d[\\\\w.+-]*)*|latest|\\\\*|)$'"
  ],
  [
    "INVISIBLE",
    "str",
    32,
    "'[\\u200b-\\u200f\\u2028\\u2029\\xad\\ufeff\\x0b\\x0c\\x1c\\x1d\\x1e\\x85\\u2060-\\u2064\u034f\\u180e\\u061c\\u202a-\\u202e\\u2066-\\u2069]'"
  ],
  [
    "CODE_SPAN",
    "str",
    32,
    "'(`+)(?:(?!\\\\1)[\\\\s\\\\S])*?\\\\1'"
  ],
  [
    "ENTITY",
    "str",
    32,
    "'(?<!\\\\\\\\)&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);?'"
  ],
  [
    "STRICT_ENTITY",
    "str",
    32,
    "'(?<!\\\\\\\\)&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});'"
  ],
  [
    "NOT_TICK",
    "str",
    32,
    "'[^`]'"
  ],
  [
    "X_RUN",
    "str",
    32,
    "'x{2,}'"
  ],
  [
    "ENTITY_UNIT",
    "str",
    32,
    "'&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);?'"
  ],
  [
    "DASH_LOOKALIKES",
    "str",
    32,
    "'[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]'"
  ],
  [
    "INLINE_TAG",
    "str",
    34,
    "'</?(b|i|em|strong|s|del|u|span|sub|sup|small|code|br|kbd|mark|abbr)(\\\\s[^<>]*)?/?>'"
  ],
  [
    "LINK",
    "str",
    32,
    "'\\\\[([^\\\\]]*)\\\\]\\\\([^)]*\\\\)|\\\\[[^\\\\]]*\\\\]\\\\([^)]*\\\\Z|\\\\[[^\\\\]]*'"
  ],
  [
    "MARKUP",
    "str",
    32,
    "'[\\\\[*_`]'"
  ],
  [
    "CODE_RUN",
    "str",
    32,
    "'`+'"
  ],
  [
    "IMAGE",
    "str",
    32,
    "'!\\\\[[^\\\\[\\\\]]*\\\\]\\\\([^()]*\\\\)'"
  ],
  [
    "ESCAPED_MARK",
    "str",
    32,
    "'\\\\\\\\([\\\\\\\\\\\\[\\\\]()*_!])'"
  ],
  [
    "AUTOLINK",
    "str",
    32,
    "\"<[A-Za-z][A-Za-z0-9.+-]{1,31}:[^\\\\x00-\\\\x20<>]*>|<[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\\\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*>\""
  ],
  [
    "HTML_TAG",
    "str",
    32,
    "'</[A-Za-z][A-Za-z0-9-]*[ \\\\t\\\\n\\\\v\\\\f\\\\r]*>|<[A-Za-z][A-Za-z0-9-]*(?:[ \\\\t\\\\n\\\\v\\\\f\\\\r]+[A-Za-z_:][A-Za-z0-9_.:-]*(?:[ \\\\t\\\\n\\\\v\\\\f\\\\r]*=[ \\\\t\\\\n\\\\v\\\\f\\\\r]*(?:[^ \\\\t\\\\n\\\\v\\\\f\\\\r\\\\\"\\'=<>`]+|\\'[^\\']*\\'|\\\\\"[^\\\\\"]*\\\\\"))?)*[ \\\\t\\\\n\\\\v\\\\f\\\\r]*/?>'"
  ],
  [
    "DECLARATION",
    "str",
    32,
    "'<![A-Z]+[ \\\\t\\\\n\\\\v\\\\f\\\\r]'"
  ],
  [
    "FILTERED_TAG",
    "str",
    32,
    "'</?(?i:title|textarea|style|xmp|iframe|noembed|noframes|script|plaintext)(?=[ \\\\t\\\\n\\\\v\\\\f\\\\r>]|/>)'"
  ],
  [
    "FOREIGN_TAG",
    "str",
    32,
    "'<(?i:svg|math)[ \\\\t\\\\n\\\\f/>]'"
  ],
  [
    "ASCII_LETTER",
    "str",
    32,
    "'[A-Za-z]'"
  ],
  [
    "EMPTY_LINK",
    "str",
    32,
    "'\\\\[\\\\]\\\\([^)]*\\\\)'"
  ],
  [
    "WORD_CHAR",
    "str",
    32,
    "'\\\\w'"
  ],
  [
    "NON_WORD",
    "str",
    32,
    "'[\\\\W_]+'"
  ],
  [
    "LETTER",
    "str",
    32,
    "'[^\\\\W_]'"
  ],
  [
    "LINK_TEXT",
    "str",
    32,
    "'(?<!\\\\\\\\)\\\\[([^\\\\[\\\\]]*)\\\\]\\\\(\\\\s*(?!<)(?:[^()\\\\s\\\\\\\\]|\\\\\\\\.|\\\\((?:[^()\\\\s\\\\\\\\]|\\\\\\\\.)*\\\\))*\\\\s*\\\\)'"
  ],
  [
    "SHOWS_NOTHING",
    "str",
    32,
    "'(?<!\\\\\\\\)(?:!\\\\[(?:[^\\\\[\\\\]\\\\\\\\]|\\\\\\\\.|\\\\[[^\\\\[\\\\]]*\\\\])*\\\\]|\\\\[\\\\])\\\\(\\\\s*(?!<)(?:[^()\\\\s\\\\\\\\]|\\\\\\\\.|\\\\((?:[^()\\\\s\\\\\\\\]|\\\\\\\\.)*\\\\))*\\\\s*\\\\)'"
  ],
  [
    "TICK_IN_DESTINATION",
    "str",
    32,
    "'\\\\]\\\\((?:[^()\\\\s\\\\\\\\`]|\\\\\\\\.)*`'"
  ],
  [
    "COMMENT",
    "str",
    48,
    "'<!--(?!>|->).*?-->|<!--(?!>|->).*\\\\Z'"
  ],
  [
    "PLAIN_LINK",
    "str",
    32,
    "'!?\\\\[[^\\\\[\\\\]<>`*_~\\\\\\\\]*\\\\]\\\\((?:[^()\\\\s<>`\\\\\\\\]|\\\\([^()\\\\s<>`\\\\\\\\]*\\\\))*\\\\)'"
  ],
  [
    "LINE_BREAK",
    "str",
    34,
    "'</?br\\\\s*/?>'"
  ],
  [
    "PLAIN_TAG",
    "str",
    34,
    "'</?(?:b|i|em|strong|s|del|ins|u|span|sub|sup|small|code|br|kbd|mark|abbr)\\\\s*/?>'"
  ],
  [
    "CLEAN_BYTES",
    "bytes",
    0,
    "b'\\\\r|\\\\x00|\\\\xc2\\\\x85|\\\\xe2\\\\x80[\\\\xa8\\\\xa9]'"
  ],
  [
    "PSEUDO_FILE",
    "str",
    32,
    "'<[^/\\\\\\\\\\\\x00]*>'"
  ]
]
```

## Appendix B exact eleven initializers

### MANIFEST

```python
MANIFEST = re.compile(
    r"(^|/)(package(-lock)?\.json|requirements[^/]*\.(txt|lock)|pyproject\.toml|poetry\.lock|uv\.lock"
    r"|yarn\.lock|pnpm-lock\.yaml|bun\.lock)$"
)
```

### PLACEHOLDERS

```python
PLACEHOLDERS = re.compile(r"__SUB__|__VAR__|__STEP__|\x00")
```

### REQUIREMENT_LINE

```python
REQUIREMENT_LINE = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\[[A-Za-z0-9._,\s-]*\])?\s*"
    r"(?:(?:===?|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9._*+!-]+(?:\s*,\s*(?:===?|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9._*+!-]+)*)?\s*(?:;[^/@:]*)?"
    r"|--hash=sha(?:256|384|512):[0-9a-fA-F]+)$")
```

### NPM_RANGE

```python
NPM_RANGE = re.compile(r"^(?:(?:\^|~|>=?|<=?|=)?\d[\w.+-]*(?:\s*(?:\|\||-|\s)\s*(?:\^|~|>=?|<=?|=)?\d[\w.+-]*)*|latest|\*|)$")
```

### HTML_TAG

```python
HTML_TAG = re.compile(r"</[A-Za-z][A-Za-z0-9-]*[ \t\n\v\f\r]*>|<[A-Za-z][A-Za-z0-9-]*"
                      r"(?:[ \t\n\v\f\r]+[A-Za-z_:][A-Za-z0-9_.:-]*"
                      r"(?:[ \t\n\v\f\r]*=[ \t\n\v\f\r]*(?:[^ \t\n\v\f\r\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*[ \t\n\v\f\r]*/?>")
```

### DECLARATION

```python
DECLARATION = re.compile(r"<![A-Z]+[ \t\n\v\f\r]")
```

### FILTERED_TAG

```python
FILTERED_TAG = re.compile(r"</?(?i:title|textarea|style|xmp|iframe|noembed|noframes|script|plaintext)(?=[ \t\n\v\f\r>]|/>)")
```

### LETTER

```python
LETTER = re.compile(r"[^\W_]")
```

### COMMENT

```python
COMMENT = re.compile(r"<!--(?!>|->).*?-->|<!--(?!>|->).*\Z", re.S)
```

### CLEAN_BYTES

```python
CLEAN_BYTES = re.compile(rb"\r|\x00|\xc2\x85|\xe2\x80[\xa8\xa9]")
```

### PSEUDO_FILE

```python
PSEUDO_FILE = re.compile(r"<[^/\\\x00]*>")
```

