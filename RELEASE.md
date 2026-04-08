# Hermes Agent — Release Process

This document describes how to cut a release, what automation runs, and how to
handle hotfixes and rollbacks.

---

## Overview

Releases follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

| Channel | How it's built | Artifacts |
|---------|---------------|-----------|
| Git tag (`vX.Y.Z`) | GitHub Actions `docker-publish.yml` | Docker image `nousresearch/hermes-agent:X.Y.Z` + `latest` |
| `main` branch push | Same workflow | Docker image `nousresearch/hermes-agent:latest` + `:<sha>` |
| PyPI (manual) | `python -m build` + `twine upload` | `hermes-agent` package |

---

## Pre-release Checklist

Before creating a tag, verify these items locally:

```bash
# 1. Tests pass
make test

# 2. No committed secrets
make scan-secrets

# 3. Version is bumped in pyproject.toml
grep '^version' pyproject.toml

# 4. RELEASE_vX.Y.Z.md exists with the changelog
ls RELEASE_v*.md | tail -1
```

---

## Bumping the Version

Edit `pyproject.toml`:

```toml
[project]
version = "0.7.0"   # ← update this
```

Commit the change:

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.7.0"
git push
```

---

## Writing the Changelog

Create `RELEASE_vX.Y.Z.md` following the template of existing release notes
(see `RELEASE_v0.6.0.md`). The changelog is published verbatim as the GitHub
Release body.

Sections to include:
- **Highlights** — major user-facing features (1 sentence + PR link each)
- **Improvements** — smaller enhancements
- **Bug Fixes** — regressions and correctness fixes
- **Breaking Changes** — anything requiring user action (migrations, removed flags)
- **Upgrade Notes** — step-by-step for breaking changes

---

## Tagging a Release

Use `make release` to create and push the annotated tag:

```bash
make release TAG=v0.7.0
```

This runs:
```bash
git tag -a v0.7.0 -m "Release v0.7.0"
git push origin v0.7.0
```

The tag push triggers the `docker-publish.yml` workflow automatically.

---

## Automated CI/CD

### `docker-publish.yml` — Docker Build & Publish

Triggered by:
- Every push to `main` → builds and pushes `:latest` + `:<sha>`
- Every Git tag push → builds and pushes `:vX.Y.Z` + `:latest`
- Every PR to `main` → builds only (no push), smoke-tests the image

The job is **skipped on forks** (`github.repository == 'NousResearch/hermes-agent'`).

Required repository secrets:
| Secret | Description |
|--------|-------------|
| `DOCKERHUB_USERNAME` | Docker Hub account name |
| `DOCKERHUB_TOKEN` | Docker Hub access token (read/write) |

### `tests.yml` — Unit Tests

Runs on every push and PR to `main`. Uses `uv` + Python 3.11 + `pytest -n auto`.

### `supply-chain-audit.yml` — Dependency Audit

Runs periodically and on PRs touching `pyproject.toml`. Checks for known CVEs.

---

## Creating the GitHub Release

After the tag is pushed and the Docker workflow completes:

1. Go to **GitHub → Releases → Draft a new release**
2. Select the tag `vX.Y.Z`
3. Paste the contents of `RELEASE_vX.Y.Z.md` as the release body
4. Click **Publish release**

Publishing the release re-triggers `docker-publish.yml` with `event: release`
(this is the canonical production image push).

---

## PyPI Release (optional)

The package is not currently auto-published to PyPI. To publish manually:

```bash
# Build
python -m build

# Upload (requires ~/.pypirc or TWINE_* env vars)
twine upload dist/hermes_agent-X.Y.Z*
```

---

## Hotfix Process

For urgent fixes that can't wait for the next planned release:

1. Branch from the tag: `git checkout -b hotfix/X.Y.Z+1 vX.Y.Z`
2. Apply the fix, add a test
3. Bump the patch version in `pyproject.toml`
4. Open a PR targeting `main`
5. After merge, tag normally: `make release TAG=vX.Y.Z+1`
6. Cherry-pick onto any active release branches if applicable

---

## Rollback

Docker images are immutable and tagged by git SHA. To roll back:

```bash
# Pull the previous image by SHA
docker pull nousresearch/hermes-agent:<previous-sha>

# Or by version tag
docker pull nousresearch/hermes-agent:v0.6.0
```

To retract a broken release:
1. Delete the GitHub Release (keeps the tag for history)
2. Force-push `:latest` to the previous SHA:
   ```bash
   docker pull nousresearch/hermes-agent:v0.6.0
   docker tag nousresearch/hermes-agent:v0.6.0 nousresearch/hermes-agent:latest
   docker push nousresearch/hermes-agent:latest
   ```
3. Open a new patch release with the fix

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| v0.6.0 | 2026-03-30 | Profiles, MCP server, Docker, fallback chains |
| v0.5.0 | — | See `RELEASE_v0.5.0.md` |
| v0.4.0 | — | See `RELEASE_v0.4.0.md` |
| v0.3.0 | — | See `RELEASE_v0.3.0.md` |
| v0.2.0 | — | See `RELEASE_v0.2.0.md` |
