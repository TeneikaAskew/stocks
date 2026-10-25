---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "test_registry_literal_pattern_initialization_is_exact fails on the eager baseline and passes for exactly the eleven approved factories, preserving all53 baseline pattern values, types and flags and all42 untouched eager initializers."
  - "test_registry_literal_patterns_preserve_native_verdicts and test_registry_literal_patterns_compile_exhaustively retain first/repeated-use, malformed-literal, dependency/shell/HTML/Unicode/bytes and native renderer-fence accepted/refused and own-import controls, with every original test, assertion, parameter and native gate/hook invocation unchanged."
  - "Matched complete original native BASE suites demonstrate a net wall-clock improvement with honest CPU/dispatch evidence; the complete proposed serial suite stays below285seconds, BASE below600seconds, and actual current-head hosted registry completes its exporter under the unchanged five-minute job timeout."
  - "Own product records, fresh ordinary declared-note source proof, full-default main/proposed no-new audits, four independent prepush reviews, authenticated current-head external reviews and all required CI are complete before merge."
status: approved
supersedes: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-read-batching.md
---

# Deferred initialization of eleven immutable registry patterns

## Decision and authority

The owner approved this design on October 24, 2026, at reviewed head `2f887b0f1db00f37be3166fba74459c3ff717410`. The owner also authorized requesting GitHub Codex review and merging this specification only after required reviews and checks pass. It contains no runtime implementation or deployment authority. Only after this specification's actual MAIN merge may its separate ready plan and initial PLANONLY draft implementation PR open. All new PRs remain drafts until the normal gates permit review.

The batching specification remains approved and unchanged at `docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-read-batching.md`; stopped private candidates and PR1579 remain preserved. The approved successor metadata names that path in `supersedes`; only this approved specification's actual MAIN merge makes the relationship effective. Do not edit the old specification, import its unreleased batching code, mark its plan done, or stack this work on its unmerged branch.

## Problem and measured opportunity

Repeated native gate process startup contributes to the registry job's five-minute pressure. A representative existing accepted-path profile attributes15.271ms to all53 explicit module-scope regex compilations together. It does not measure these eleven individually, predict their saving, or establish the complete suite's bottleneck. Their named consumer functions were absent in that single profile; this is sample-specific absence only. The separate batching comparison did not demonstrate a net full-suite improvement, so dispatch reduction is not acceptance evidence for this design.

The opportunity is to defer only immutable literal construction until the corresponding consumer first needs it. No new profile, CLI benchmark or runtime experiment is part of this specification preparation. Actual improvement is unknown and must be measured after a separately approved implementation.

## Baseline and consumer inventory

The design is bound to actual MAIN6f03ab14a7c858e741d9023f215a1bf24e0371c1. Its gate is291006bytes with SHA2562423055bd52213e20f71e4be76c5819799b39d4d5c40bcadc134359005f3e9d2. Definition and consumer line numbers below refer to that source. Appendix A records all53 baseline compiled pattern values/types/flags; it was derived by evaluating only their literal/static source expressions with Python's ordinary regex engine, without importing or running the gate. Exact source initializers of the eleven are pinned in Appendix B. Adjacent literal concatenation and every escape, including counterintuitive escapes, remain exact; no pattern simplification is authorized.

| Existing binding | Initializer line | Proposed zero argument factory | Existing consumer and method | Pattern type | Compiled flags |
| --- | ---: | --- | --- | --- | ---: |
| MANIFEST | 99 | _manifest_pattern | chore_allows:1742, search | str | 32 |
| PLACEHOLDERS | 460 | _placeholders_pattern | shell_statements:505, search | str | 32 |
| REQUIREMENT_LINE | 1632 | _requirement_line_pattern | non_dependency_edit:1687, match | str | 32 |
| NPM_RANGE | 1636 | _npm_range_pattern | dependency_values:1657, match | str | 32 |
| HTML_TAG | 2773 | _html_tag_pattern | raw_html:2861, match | str | 32 |
| DECLARATION | 2776 | _declaration_pattern | raw_html:2855, match | str | 32 |
| FILTERED_TAG | 2777 | _filtered_tag_pattern | raw_html:2862, match | str | 32 |
| LETTER | 3008 | _letter_pattern | read_index:3152, finditer | str | 32 |
| COMMENT | 3396 | _comment_pattern | uncommented:3402, sub | str | 48 |
| CLEAN_BYTES | 3889 | _clean_bytes_pattern | document_refusal:3953, search | bytes | 0 |
| PSEUDO_FILE | 4024 | _pseudo_file_pattern | render_fence.fence:4038, fullmatch | str | 32 |

There are eleven direct runtime loads across nine owning gate functions. No target participates in another initializer; all eleven compile arguments are immutable string/bytes literals, with COMMENT's explicit `re.S` and the existing inline flags preserved.

The tracked-repository consumer search included every Python file, tests, workflows and hooks, direct name/attribute references, `import spec_gate`, dynamic module loaders and string-based target names. No external direct consumer of these eleven bindings, nor target-specific `.pattern`, `.flags`, `isinstance`, `is` or dictionary-lookup assumption, was found. `tests/scripts/test_spec_gate.py` imports/loads the gate and exercises its functions; its existing tests have no direct reference to these target names. External production module readers `scripts/maintenance/doc_source_snapshot.py` use BRANCH, frontmatter, validate_plan_body and source_import_shadow; `scripts/maintenance/docs_audit.py` uses source_import_shadow. These functions and BRANCH are outside this change. `tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py`, `tests/scripts/test_export_model_registry.py` and `tests/scripts/measure_inventory_render.py` are neighboring consumers to validate, not source paths this design may edit. Other COMMENT/LETTER occurrences are unrelated comments or `tokenize.COMMENT`.

This search establishes the tracked MAIN boundary, not absence of out-of-repository or future reflective users. The proposed change removes these private eager pattern globals in favor of private factories; it does not preserve an undocumented `module.MANIFEST`-style export. Approval must include that explicit compatibility choice. If implementation-time inventory discovers any additional direct/reflective consumer or identity contract, stop and narrow/revise the design before implementing it; do not add a proxy, module `__getattr__`, compatibility import or wider rewrite silently.

## Proposed construction and call contract

Replace only each selected assignment, in its existing source location, with a zero-argument private factory named in the table. Decorate each with the already-imported `functools.lru_cache(maxsize=1)`. Its body returns `re.compile` with the exact original literal expression and exact positional/inline flags; no supplied pattern, name, text, environment, path, Git content or policy result enters it. String factories return real `re.Pattern[str]`; CLEAN_BYTES returns real `re.Pattern[bytes]`. No proxy object, alternate regex engine, default argument eager compilation or catch-and-accept fallback is permitted.

Each process retains at most one compiled object per factory, at most eleven cache entries total, keyed only by the empty argument tuple. First successful use produces the ordinary pattern. Repeated sequential use returns that same real object; clearing the unrelated `re` module cache must not discard the retained object. No cross-process, file, bytecode or policy/input cache exists. Concurrent first-use identity beyond the existing single-threaded CLI is not a new promised API; all returned objects must retain identical immutable pattern semantics and only one cached result per factory.

At the ten ordinary consumer load sites, substitute the corresponding zero-argument factory call at the same method-call location, retaining the original method, arguments, evaluation order, branches, loops and diagnostics. For PSEUDO_FILE only, materialize `_pseudo_file_pattern()` once at `render_fence(root)` factory entry and capture the real pattern in its existing `fence` closure. The existing callback's fullmatch uses that captured pattern. This ensures compilation occurs before the audit hook is registered, rather than introducing first-use compilation or cache acquisition inside the audit callback. All fence acceptance/refusal rules, pseudo-filename handling and exit codes remain unchanged.

All other42 explicit eager regex assignments remain byte-for-byte unchanged. Existing import order/ownership, source compilation, module/file layout and all other function bodies remain unchanged except these consumer substitutions and the PSEUDO_FILE capture. No new import, generic pattern-name dispatcher, configuration switch, source rewrite loader or alternate gate entrypoint is permitted. Runtime source is only `scripts/gate/spec_gate.py`; meaningful regressions are appended only to `tests/scripts/test_spec_gate.py` under its existing no-decorator/no-skip/no-return-or-raise suite rules.

## Regression and negative controls

Add `test_registry_literal_pattern_initialization_is_exact`: the eager baseline fails because the eleven deferred factories are absent and selected literals compile during module initialization. On the proposed source, observe zero selected literal compilations at import, exercise all eleven factories explicitly, then prove real `re.Pattern` type, exact `.pattern` value and its str/bytes type, `.flags`, `.groups` and `.groupindex` against the independent baseline53 inventory. Pin Appendix A as a literal inline fixture in tests/scripts/test_spec_gate.py; never recompute the expected values solely from the proposed module or its factories. Prove all42 unselected eager initializers and every original test function/class AST, parameter, assertion and native gate/hook call are unchanged. Instrumentation is test-only and never a production environment branch.

Add `test_registry_literal_patterns_compile_exhaustively`: first use and repeated sequential use, `re.purge()` behavior, zero-argument signatures, at-most-one cache entry each, exact8bit/Unicode/inline/explicit flag behavior and exhaustive construction of all53 families. Meaningful negative controls must make the test fail for an unvisited invalid literal, changed explicit or inline flag, str/bytes substitution, a changed unselected initializer, an eager factory default argument, or a factory accepting/caching a mutable input. Compare baseline methods' actual match spans/groups/substitution results for empty, malformed, Unicode and bytes inputs; do not derive both sides solely from the new factories. Invalid-literal mutation is a regression control, not authority to admit an invalid production literal merely because one ready path never uses it.

Add `test_registry_literal_patterns_preserve_native_verdicts`: same assembled baseline/proposed accepted ready actionlint case and explicit follow-up refusal, plus existing chore dependency-only acceptance and URL/executable/version refusal, shell placeholder/runtime-input override refusal, HTML comment/tag/filtered-tag and malformed-markup refusal, Unicode letter/deferral and raw-byte documentation checks. Preserve baseline diagnostic class/order and exact exit/verdict. Exercise the native renderer fence: integer file descriptors and its existing pseudo-filename rules remain accepted, while real outside-root/symlink escapes retain the original refusal/exit behavior. The PSEUDO_FILE factory must be resolved before hook registration; a control that first constructs it inside the hook must be detected. Source-module/import shadow controls, actual renderer/verifier refusal controls and all original native invocations remain mandatory. No missing branch may be hidden by conditional assertions or collection skips.

The baseline reference must remain available in shallow Backtest checkouts without extra network/fetch: a test-only reversal of only these eleven factories and their exact consumer substitutions may reconstruct the full original source, but must assert the exact baseline SHA256 above before running that ordinary uncompiled CLI. No alternate compiled gate/test harness is accepted. Preserve all actual original test names, parameters, assertions and native calls. Before any edit, retain exact baseline source/suite and failing capacity evidence privately.

No Git/input acquisition change is included: original Tree/policy/fallback code stays byte-identical. Tests must still prove repository/config/replacement/index/worktree mutations remain visible through the existing native paths, while the regex-only factories keep no text or verdict state. The stopped batching helper/callers must be absent from this implementation branch.

## Performance acceptance and stop

Run focused genuine RED/GREEN controls and the required neighboring unchanged exporter/source/audit/renderer suites. Measure the complete original BASE suite against baseline and proposed source with identical full suite bytes, native command, Python/environment/resource conditions, wall/child CPU and subprocess counts, without concurrent CPU tests. The exact serial command stays:

```text
python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest
```

Do not compare different case counts as net speed proof. Separately run the complete proposed suite containing every original and meaningful new case once the matched result permits proceeding. No selected-case result substitutes for full acceptance. A microprofile or the15.271ms all53 aggregate cannot be multiplied into a predicted eleven-pattern or full-suite saving.

Require demonstrable positive net matched original-suite wall improvement and successful complete proposed suite below285seconds, unchanged BASE suites below600seconds, and actual exact-head hosted registry including exporter under its unchanged300second whole-job timeout. Local timing does not certify hosted capacity; inspect exact-head stage logs and terminal conclusions. If net improvement is absent or any required capacity gate cannot be met, stop, preserve the candidate/evidence and report the shortfall. No blind retry, deadline increase, omitted cases, worker flags, source-compilation shortcut or undisclosed faster harness follows.

Renderer60second/512MiB and verifier5second/8MiB/20000-entry limits remain exact. No dependency, runner/workflow/pin/hook, branch-protection, import trust, command grammar, GCP/provider, STRAT/options or product runtime change is included. Source compile and module imports still run normally in each CLI process.

## Delivery and close-out

After actual approved-spec MAIN merge only: use one new branch/author/ready plan; gated initial PLANONLY commit, one draft PR, gated PLANONLY binding of its real number, then CODE. No stacking on PR1579 or another unmerged proposal. The sole runtime edit and regression paths are above. Own delivery edits are its plan, FEAT-CICD-001 catalog/traceability records, the existing SHARED-01 implementation-source note in place preserving inventory/verifier context, and fresh ordinary declared-note sidecar under the independently approved declaration. No documentation admission/governance policy change is part of this design.

The final frozen head owes four independent prepush seats: shell semantics, YAML/Actions, exporter/policy, and byte/identity/freshness. Each executes a concrete scoped negative control rather than inferring safety from unchanged text. Fix confirmed findings in one complete batch, re-review the scoped correction, then root releases one sole-author CODE push. Require ordinary full-default main/proposed no-new audits, BASE/proposed PR gates, authenticated current-head CODE/security review, all required CI and resolved conversations under the two-round cap. Actual implementation merge needs separately verified owner authority.

After any eventual authorized implementation merge, independently verify actual MAIN source/body, accepted/refused behavior and no-new audit using a fresh network-only clone. Complete the existing ordinary current-trunk DOC stamp and source-sidecar retirement only with real current-source proof, then separate status-only plan closure. No pending CODE result, local identity or private checkpoint is production verification. Fixture/COMMON/DATA prerequisites remain their own workflow boundaries; this specification does not complete them or authorize deployment.

## Capacity and risks

Volume: eleven fixed literal factories and at most eleven retained compiled objects per CLI process, plus all144 original baseline cases and meaningful new cases; no product rows. Velocity: no provider/SQL calls and no change to Git dispatch semantics; potential avoided regex construction depends on actual exercised consumers. Wall-clock: individual eleven-pattern cost and net suite saving are unknown. Cost: no new GCP resources/schedules/dependencies; ordinary CI usage remains and must be measured.

Primary risks are moving compile errors to an unvisited branch, wrong literal/inline flags or bytes type, losing a private external consumer, cache overhead erasing the gain, and creating first-use work inside the renderer audit hook. Exact source/value/type/flags/consumer inventory, exhaustive negative controls, pre-hook PSEUDO_FILE capture and matched full native/hosted measurements govern acceptance. If a candidate cannot meet them within this scope, reject or seek a separate design; do not widen the eleven targets.

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

