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
   `https://raw.githubusercontent.com/<repo>/main/<source_json>`. Record `source_sha` from the file.
   If the user points at a branch or an open PR, refuse: "Canvases track main. Merge first."
   If `source_json` is null for that canvas, stop and say the exporter does not exist yet; offer to compare
   the canvas against `source_docs` by hand and report differences without writing.

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

4. **Show the diff in chat before writing anything.** Format:

       Stocks models diagram <- main @ <sha> (registry last reviewed <date>)
       ADD     MODEL-NEW-001 (status Experimental)
       CHANGE  MODEL-EXIT-001.status  "Broken" -> "Production but needs remediation"
       CHANGE  MODEL-MAG-001.verdict  "..." -> "..."
       REMOVE? MODEL-OLD-001 (not in registry; left in place, say "remove" to drop it)
       unchanged: 31 cards

   If the diff is empty, say so and stop. Do not write.

5. **Wait for the user.** "go", "apply", "yes" applies everything listed except REMOVE? rows.
   "go, remove MODEL-OLD-001" also drops that card. Anything else: apply only what they name.

6. **Write.** Rebuild the `var <constant> = [...]` line with the merged array, serialized as JSON on
   one line exactly as the original was. Change nothing else in the file. Update the provenance footer
   text ("registry last reviewed ...") if the board has one and the date changed. Publish with the
   Artifact tool: action `publish`, `url` = the canvas url, `file_path` = the edited board file
   (and `files` for additional boards). This is a save, not a public share; the canvas stays private.

7. **Report.** One line per board: what changed, the source sha, and that layout was not touched.

## Guardrails

- One canvas per run. If the user asks for all three, run them one after another with a diff and an
  approval each.
- Never regenerate the whole data array from the JSON. The canvas-owned fields (`sched` ordering, `ratText`,
  `bucket`, `flow`, `stage`, `short`, `alert`) are curation; a regeneration destroys them.
- Never edit `index.html`, `canvas.json`, `artifact-type/`, or any CSS/HTML outside the data line.
- If the JSON `source_branch` is not `main`, refuse. If the file is older than the registry's
  "Last reviewed" date, say the exporter needs a re-run on main first.
- Do not chain this into a PR, a webhook, or a scheduled task. It runs when a person asks.
