# 30-second demo

![MemPatrol terminal demo](demo.gif)

The GIF is generated from **real CLI output** on a small **synthetic** demo DB
(no production memory text). 32.1 s, 321 rendered frames, 960x540 (GIF optimization keeps 30s+ playback).

## Reproduce

```bash
python scripts/demo_setup.py /tmp/mem-patrol-demo/demo.db
python scripts/make_demo_gif.py        # writes docs/demo.gif
bash scripts/demo.sh                   # prints the same commands to stdout
```

`scripts/demo.sh` runs: version → diagnosis → recall bench (6/6) → `memorix recall`.

## What it shows

1. `memorix --version` — `mem-patrol 0.3.5`
2. `memorix diagnose` — 12 synthetic memories, type distribution, findings
3. `memorix.retrieval.bench` — §10.3 cases 6/6
4. `memorix recall` — prompt-ready block for a synthetic memory

For a live terminal recording, `asciinema rec docs/demo.cast -c "bash scripts/demo.sh"`
(or use the GIF above in the README).
