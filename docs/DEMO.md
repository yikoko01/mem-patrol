# 30-second demo

![MemPatrol terminal demo](demo.gif)

The GIF is generated from **real CLI output** on a small **synthetic** demo DB
(no production memory text). 30.1 s, 155 frames, 960x540.

## Reproduce

```bash
python scripts/demo_setup.py /tmp/mem-patrol-demo/demo.db
python scripts/make_demo_gif.py        # writes docs/demo.gif
bash scripts/demo.sh                   # prints the same commands to stdout
```

`scripts/demo.sh` runs: version → diagnosis → recall bench (6/6) → policy eval (9/9).

## What it shows

1. `memorix --version` — `mem-patrol 0.3.0`
2. `memorix diagnose` — 12 synthetic memories, type distribution, findings
3. `memorix.retrieval.bench` — §10.3 cases 6/6
4. `memorix.eval --suite policy` — 9/9

For a live terminal recording, `asciinema rec docs/demo.cast -c "bash scripts/demo.sh"`
(or use the GIF above in the README).
