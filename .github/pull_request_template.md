## What changed

## Why

## Checklist

- [ ] `pytest -p no:cacheprovider` passes
- [ ] `python -m memorix.eval --suite all --baseline eval/baseline.json` passes
- [ ] benches pass (6/6 recall, 9/9 judge)
- [ ] no host-specific imports / no production data / no secrets
- [ ] read-only default + `--apply` + backup invariant preserved
- [ ] CHANGELOG updated for user-visible changes
