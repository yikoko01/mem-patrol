# PyPI publishing

Distribution: **`mem-patrol`**. GitHub Release already works; PyPI is a separate gate.

## Option A — trusted publishing (recommended, no token in secrets)

1. On PyPI: project **mem-patrol** → *Publishing* → **Add a pending publisher**
   - owner: `yikoko01`
   - repository: `mem-patrol`
   - workflow: `publish.yml`
   - environment: `pypi`
2. In GitHub repo: Settings → Environments → create **`pypi`** (no secrets needed).
3. Actions → **publish-pypi** → *Run workflow* (or re-run after a tag).
   The workflow builds `dist/` and uses OIDC (`id-token: write`) to upload.

## Option B — API token

```bash
python -m build
python -m twine check dist/*
TWINE_USERNAME=__token__ TWINE_PASSWORD=<pypi-token> python -m twine upload dist/*
```

## Current state

- GitHub release `v0.2.3` (or latest) is the source of truth.
- PyPI upload is **not done yet** (no trusted publisher configured / no token).
- `publish.yml` is `workflow_dispatch` only, so a tag push will not fail if PyPI
  is not configured.

## Notes

- PyPI names are global; `memorix` is already taken, this project uses `mem-patrol`.
- Do not commit API tokens; prefer trusted publishing.
