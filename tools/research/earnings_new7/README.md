# Local-only seven-ticker earnings/news reproduction

These are the actual first-party source scripts used for FDX, LLY, STX, INTC,
AMD, TWLO and VLO, with separately identified portability adaptations. Original
bytes remain in the owner's private recovery evidence; `source-identities.json`
records each original and adapted digest. This finite set does not preserve or
publish all 663 historical source versions. It is not a production pipeline.

Pure formula functions are retained byte-for-byte. The two imported rule modules
have their obsolete standalone ten-ticker/old-protocol runners removed. There
is no provider client, acquisition fallback or automatic credential discovery.
`render_delivery.py` no longer packages restricted source responses. Outputs
are retrospective vendor-only descriptive research, not publisher-qualified PIT
news, a directional forecast, performance proof or financial advice.

The owner must privately supply the original hash-verified news responses,
sanitized acquisition receipt, original code-freeze manifests and source files,
frozen event protocol, selected daily projections and their frozen input
manifests. No raw licensed article body, raw OHLC path, credential, or private
capture manifest is included here. This is an explicit private-input dependency,
not a claim that the public repository alone reproduces the market experiment.

Use a fresh private working directory with those inputs (the original scripts
refuse to overwrite completed result directories). Each stage remains separate:

```sh
python tools/research/earnings_new7/analyze_news_once.py --input-root PRIVATE_DIR --path-map PRIVATE_MAP.json
python tools/research/earnings_new7/join_and_describe_once.py --input-root PRIVATE_DIR --path-map PRIVATE_MAP.json
python tools/research/earnings_new7/render_delivery.py --input-root PRIVATE_DIR --path-map PRIVATE_MAP.json
```

The optional mapping is a JSON object mapping old absolute input prefixes to
owner-local directories. A saved source freeze verifies ORIGINAL source files
in the private input directory; the adaptation's own identity is separately
recorded in `source-identities.json`. Preserve both identities in any rerun.
Do not substitute today's inputs, recompute vendor scores or change dates/bins.

The news stage runs before the outcome join. It applies exact target-ticker
scores, fixed 48-hour pre-release windows, deterministic deduplication, explicit
empty/missing/capped states and the original fixed sentiment thresholds. The
join computes exactly two Spearman correlations and the existing 35 sampled
DAILY episodes. A first opposite closing step is not full reversal, continuous
intraday duration, a native `is_reversal_5d` replacement or a probability.
The renderer creates derived chart/table output only; it does not upload.

`tests/research/test_earnings_new7_reproduction.py` validates synthetic controls
and import purity without opening private market data or rerunning old results.
