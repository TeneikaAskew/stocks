# Hand-maintained copies of the auto-refreshed documents

The monthly `refresh-architecture-docs` workflow rewrites four documents in
place: `../05-a-ARCHITECTURE.md`, `../05-c-DATA_DEPENDENCIES.md`,
`../05-d-COST_ANALYSIS.md` and the repository `README.md`. This folder holds
the hand-edited version of each, taken on 2026-09-08 before the first refresh
that runs on the rendered-graph pipeline, so the manually written text is
never overwritten:

| here | refreshed copy |
|---|---|
| `05-a-ARCHITECTURE.md` | `../05-a-ARCHITECTURE.md` |
| `05-c-DATA_DEPENDENCIES.md` | `../05-c-DATA_DEPENDENCIES.md` |
| `05-d-COST_ANALYSIS.md` | `../05-d-COST_ANALYSIS.md` |
| `ROOT-README.md` | `../../../../README.md` |

Nothing automated writes here. The workflow's write policy names exactly the
four refreshed files, its stray-write scan fails the run on any other change,
`scripts/verify_docs_against_live.py` enrols `docs/product/infrastructure/*.md`
only (not this folder), and the prompts tell the model this folder is
off-limits. Relative links in the copies were rebased one directory deeper so
they still resolve from here.

Edit these copies by hand when you want to. To refresh a copy from the live
version, copy the file over and rebase its links again: every relative link
target gains one leading `../`.
