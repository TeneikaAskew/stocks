# Hand-maintained 2026-09-08 copies of four documents

The scheduled `refresh-architecture-docs` workflow, whose retirement the owner
decided on 2026-11-10, rewrote four documents in place:
`../05-a-ARCHITECTURE.md`, `../05-c-DATA_DEPENDENCIES.md`,
`../05-d-COST_ANALYSIS.md` and the repository `README.md`. This folder holds
the hand-edited version of each, a snapshot taken on 2026-09-08 before the
first refresh that ran on the rendered-graph pipeline, so the manually written
text could not be overwritten. The originals have been maintained by hand
since. The copies and their originals:

| here | refreshed copy |
|---|---|
| `05-a-ARCHITECTURE.md` | `../05-a-ARCHITECTURE.md` |
| `05-c-DATA_DEPENDENCIES.md` | `../05-c-DATA_DEPENDENCIES.md` |
| `05-d-COST_ANALYSIS.md` | `../05-d-COST_ANALYSIS.md` |
| `ROOT-README.md` | `../../../../README.md` |

Nothing automated writes here. The workflow's write policy named exactly the
four refreshed files, its stray-write scan failed the run on any other change,
and its prompts told the model this folder was off-limits;
`scripts/verify_docs_against_live.py` enrols `docs/product/infrastructure/*.md`
only (not this folder). Relative links in the copies were rebased one
directory deeper so they still resolve from here.

Edit these copies by hand when you want to. To refresh a copy from the live
version, copy the file over and rebase its links again: every relative link
target gains one leading `../`.
