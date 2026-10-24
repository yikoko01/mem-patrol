# Real-corpus regression (privacy-preserving)

The synthetic §10.3 fixture (`eval/baseline.json`) catches algorithm changes, but it is
not production text. `eval/real_corpus.json` adds a **real-snapshot gate** without storing
any production text:

- snapshot SHA-256 (so the check fails on a different/edited DB);
- query strings + `as_of_ts` + expected memory ids;
- SHA-256 of each expected memory's normalized content (no `content` field).

## Run

```bash
python -m memorix.eval.real_corpus \
  --db /path/to/read-only-snapshot.db \
  --user-id <private-chat-user-id> \
  --manifest eval/real_corpus.json \
  --schema examples/self-learning.schema.json
# REAL_CORPUS PASS / FAIL, exit 1 on failure
```

- The snapshot is **never** committed; only its hash is.
- `--user-id` is supplied at runtime (not stored in the manifest).
- On snapshot hash mismatch the check fails before touching recall.
- Content-hash mismatch also fails, so a changed memory is visible without leaking it.

## What is the historical data gap?

`case3-versions` asks *why 8-23 was harder than 8-19*. At that cutoff the corpus had no
single memory comparing the two dates: the 8-19 evidence was about a root cause that could be
verified from code/logs, while 8-23 was a blind-change period (no logcat, not reproducible).
The comparison memory was added **after** the question (and is excluded by point-in-time
replay), so historical replay stays 5/6; current replay is 6/6. This is a data gap, not a
scorer failure. No raw production text is stored here.

## Updating

Copy the new snapshot hash and expected content hashes into the manifest, review the diff,
and keep the old manifest in git history as the regression contract.

## CI

CI does not have your snapshot, so this is an opt-in local/CI-with-secret step. A future
job can fetch a private snapshot and run this command; the synthetic suite stays hermetic.
