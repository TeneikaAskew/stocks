---
name: refresh-canvas
description: Refresh a Claude Design canvas (the Stocks models diagram, the backend architecture diagram, the Solyra structure diagram) from what is on the repo's main branch. Use whenever the user says refresh, update, sync, or "bring the diagram up to date", or after a PR touching docs/product/07-MODEL-REGISTRY.md merges. Requires the Artifact tool, so it runs in claude.ai chat or Claude Code on the web, never in a terminal session or CI. Diff first, write only after the user approves, replace data blocks only, never layout.
---

# Refresh a canvas from main

The canvases are hand-designed. The repo owns some fields on each card; the canvas owns the rest.
This skill updates only the repo-owned fields, shows the diff, and writes only on approval.

Config: `docs/product/canvases.yml` in the stocks repo. Read it first. Each entry names the canvas URL,
the JSON that feeds it, which board file and JS constant hold the data, and which fields the repo owns.

## Steps

1. **Confirm the source is main.** Fetch `source_json` from
   `https://raw.githubusercontent.com/<repo>/main/<source_json>`. Record `sources` from the file: the git
   blob id of each source document the JSON was exported from.
   If the user points at a branch or an open PR, refuse: "Canvases track main. Merge first."
   If the canvas is `mode: report-only` (its `source_json` is null), no exporter exists: compare the
   canvas against `source_docs` by hand and report the differences. Never write a report-only canvas.

2. **Read the canvas.** Artifact tool, action `read`, with the canvas `url`. Open each board file listed
   under `boards`. Locate the `var <constant> = [...]` line. Parse the JSON array that follows it.
   That array is the canvas data. If the constant is not found, stop; the canvas layout changed and
   `canvases.yml` needs updating first.

3. **Compute the diff, per board.** Key both sides by `key`. For every id:
   - present in JSON, absent on canvas: ADD (new card, fill repo_fields from JSON, leave canvas_fields empty)
   - present on canvas, absent in JSON: REMOVE candidate (do not remove automatically; list it)
   - present in both: for each field in `repo_fields`, compare; list changed fields old -> new.
   Never compare or touch anything in `canvas_fields`.
   Where a repo field is a list (code paths, schedulers), compare as sets.
   A repo field whose JSON value is null is **not sourced** for that card: the registry has no column
   for it in that tier. Never overwrite the canvas value with it; list it under `not sourced`.
   A field declared with `merge: ordered_set` (`sched`) is repo-owned for membership and canvas-owned
   for order: keep the canvas's existing entries in their order, drop entries the JSON no longer has,
   and append new ones at the end.

4. **Show the diff in chat before writing anything.** Format:

       Stocks models diagram <- main (07 blob <id>, registry last reviewed <date>)
       ADD     MODEL-NEW-001 (status Experimental)
       CHANGE  MODEL-EXIT-001.status  "Broken" -> "Production but needs remediation"
       CHANGE  MODEL-MAG-001.verdict  "..." -> "..."
       REMOVE? MODEL-OLD-001 (not in registry; left in place, say "remove" to drop it)
       not sourced: MODEL-LLM-001.name, MODEL-LLM-001.doc (null in the registry; canvas kept)
       unchanged: 31 cards

   If the diff is empty, say so and stop. Do not write.

5. **Wait for the user.** "go", "apply", "yes" applies everything listed except REMOVE? rows.
   "go, remove MODEL-OLD-001" also drops that card. Anything else: apply only what they name.

6. **Write.** Rebuild the `var <constant> = [...]` line with the merged array, serialized as JSON on
   one line exactly as the original was. Change nothing else in the file. Update the provenance footer
   text ("registry last reviewed ...") if the board has one and the date changed. Publish with the
   Artifact tool: action `publish`, `url` = the canvas url, `file_path` = the edited board file
   (and `files` for additional boards). This is a save, not a public share; the canvas stays private.

7. **Report.** One line per board: what changed, the source blob ids, and that layout was not touched.

## Guardrails

- One canvas per run. If the user asks for all three, run them one after another with a diff and an
  approval each.
- Never regenerate the whole data array from the JSON. The canvas-owned fields (`sched` ordering, `ratText`,
  `bucket`, `flow`, `stage`, `short`, `alert`) are curation; a regeneration destroys them. `sched` membership
  comes from the repo and is merged as an ordered set, so its order survives.
- Never edit `index.html`, `canvas.json`, `artifact-type/`, or any CSS/HTML outside the data line.
- Provenance is the URL: fetch only from `raw.githubusercontent.com/<repo>/main/...`, never a local file,
  never a branch URL. If in doubt, compare each blob id in the JSON's `sources` with the same file on main
  (`git ls-tree origin/main <path>`, or the blob `sha` the GitHub contents API returns); a mismatch means
  the exporter was not re-run for the registry now on main. CI's `--check` step makes that rare.
  If the JSON's `registry_last_reviewed` is older than the registry on main, the exporter needs a re-run first.
- Do not chain this into a PR, a webhook, or a scheduled task. It runs when a person asks.
