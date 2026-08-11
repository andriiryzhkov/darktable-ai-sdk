# CI and releasing

`dtai init` scaffolds three GitHub Actions workflows into `.github/workflows/`.
Between them they check every pull request, publish a rolling nightly, and cut
a reviewed release – all driven by the same `dtai` commands you run locally, so
a green CI run means the same thing as a clean `dtai run` on your machine.

This document covers a **model repository's** CI. The SDK's own test and PyPI
publishing setup is a separate thing, described in the SDK
[README](../README.md#releasing).

---

## The three workflows

| Workflow | Fires on | Produces |
|---|---|---|
| `check-pr.yml` | every pull request | nothing – a pass/fail signal |
| `nightly.yml` | model changes on the default branch | a rolling `nightly*` pre-release |
| `release.yml` | a `release-*` tag | a **draft** release you publish by hand |

All three start with the same `discover` job, and that job is the reason the
whole thing scales.

### One job per model

`dtai list --json-output` emits exactly what a GitHub matrix wants:

```console
$ dtai list --json-output
[{"id": "denoise-nafnet", "dep_group": "nafnet"}, {"id": "upscale-bsrgan", "dep_group": "bsrgan"}]
```

The `discover` job captures that into an output, and the build job fans out
over it:

```yaml
strategy:
  fail-fast: false
  matrix:
    include: ${{ fromJson(needs.discover.outputs.models) }}
steps:
  - run: uv sync --group ${{ matrix.dep_group }}
  - run: uv run dtai setup ${{ matrix.id }}
```

Two consequences worth understanding:

- **Only the model's own dependencies are installed.** A model needing torch
  2.2 and one needing mmcv never share a runner, which is the whole point of
  `dep_group` – see [Handling differing dependencies](building-a-repo.md#5-handle-differing-dependencies).
- **`fail-fast: false`**, so one broken model doesn't cancel the others. You
  see every failure in one run rather than discovering them one at a time.

Models marked with a `.skip` file are absent from the JSON, so they cost
nothing in CI.

---

## `check-pr.yml`

Runs `setup` → `convert` → `validate` for each model on every pull request.
It deliberately stops short of `package`: a PR should prove the model still
builds and its ONNX still loads, not produce artifacts nobody will install.

`concurrency` cancels a previous run when you push again to the same PR, so a
branch you're actively pushing to doesn't queue up stale jobs.

It has `permissions: contents: read` and no secrets, which makes it safe to
enable for fork PRs.

The demo step is commented out in the scaffolded file. Uncomment it once the
model has a `demo.py` and `samples/<task>/` to run against:

```yaml
- name: Run demo
  run: uv run dtai demo ${{ matrix.id }}
```

---

## `nightly.yml`

Fires when anything under `models/**` lands on `main` or `master`, and rolls a
single pre-release that always points at the latest build. Testers get updated
weights without waiting for a release.

Three details that make it behave:

- **`allowUpdates: true` + `removeArtifacts: true`** – the same pre-release is
  reused each run and its old `.dtmodel` assets are deleted first, so a model
  you delete from the repo doesn't linger as a stale download.
- **`retention-days: 1`** on the build artifacts. They only need to survive
  long enough for the publish job to collect them; model packages are large
  and GitHub storage is not free.
- **The publish job requires every model to have built** (`needs.build.result
  == 'success'`). A partial nightly would hand testers a release silently
  missing models, which is worse than no nightly at all.

### The nightly channel name

The tag comes from your own `release-*` git tags, via `dtai git-version`:

```console
$ dtai git-version            # full version
5.6.0+47~gabc1234
$ dtai git-version --prefix   # the channel key
5.6.0
```

With a prefix the workflow tags `nightly-5.6.0`, which is what lets
`releases-index.json` point one darktable version at its own nightly channel.
Before your first `release-*` tag there is nothing to derive, the prefix comes
back empty, and it falls back to a single rolling `nightly`. Either way the
workflow runs – a fresh repo is not a special case.

This is also why the nightly `discover` job checks out with `fetch-depth: 0`:
`git describe` needs the tags, and Actions clones shallow by default.

---

## `release.yml`

Tag `release-<version>` and push it. Every model is built, validated and
packaged, then the archives plus `versions.json` are attached to a
**draft** release.

Draft is deliberate. Review the assets, write the notes, and publish from the
GitHub UI when you're satisfied – a published release is what darktable's
update check sees.

Running it manually from a branch (`workflow_dispatch`) builds everything but
publishes nothing, which makes it a usable dry run.

### What to bump first

```bash
# 1. bump `version:` in the model.yaml of whatever changed
# 2. commit
git tag release-1.2.0
git push origin release-1.2.0
```

Step 1 is the one people forget. darktable compares the `version` string in
`config.json` against the published `versions.json` to decide an update is
available – **an unchanged version means users keep the old weights**, however
different the archive is. There is no content hashing on that path.

---

## The two index files

Automatic download in darktable needs two JSON files, and they live in
different places.

### `versions.json` – a release asset

Generated for you by the publish job:

```bash
dtai versions --artifacts-dir artifacts
```

```json
{
  "models": {
    "upscale-bsrgan": {
      "version": "1.0",
      "sha256": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    }
  }
}
```

`version` drives update detection. `sha256` – note the mandatory `sha256:`
prefix – lets darktable verify a download and skip one rate-limited API call
per asset. Without `--artifacts-dir` only the versions are written, which is
what a PR-time sanity check wants.

The command accepts both the nested layout `actions/download-artifact`
produces and the flat `output/` layout `dtai package` writes locally, so it
works the same in CI and on your machine.

### `releases-index.json` – committed at the repo root

darktable reads it from your default branch:

```text
https://raw.githubusercontent.com/<owner>/<repo>/HEAD/releases-index.json
```

```json
{
  "schema": 1,
  "compatible_releases": {
    "5.5.0": "nightly-5.5.0",
    "5.6.0": "release-1.2.0"
  }
}
```

This maps a darktable version to the release tag it should pull assets from,
and it is the mechanism that stops a new package format reaching an old
darktable. Nothing generates it – you edit it when you publish.

A scaffolded repo ships it with `compatible_releases` empty, which means
"offer nothing". That is the correct starting state: there are no releases to
point at yet, and an entry naming a tag that doesn't exist is worse than none.

---

## Before your first green run

Three things a fresh repo needs that CI will otherwise fail on.

**Actions must be allowed to write.** `nightly.yml` and `release.yml` declare
`permissions: contents: write` for their publish steps. If your account or org
defaults workflow permissions to read-only, enable write under *Settings →
Actions → General → Workflow permissions*.

**Commit `uv.lock`.** Every workflow caches on `cache-dependency-glob:
"uv.lock"`. Without it the cache key is unstable and each job re-resolves from
scratch.

**Define every `dep_group` you reference.** CI runs `uv sync --group
<dep_group>`, and a group that isn't in `[dependency-groups]` fails
immediately:

```console
error: Group `core` is not defined in the project's `dependency-groups` table
```

`core` is the default for any model that doesn't name a group, so the
scaffolded `pyproject.toml` defines `core = []` for exactly this reason. Keep
it, even if it stays empty.

---

## Adapting them

The scaffolded workflows are a starting point, not a contract – they're
ordinary files in your repo. Common changes:

- **Big checkpoints.** `dtai setup` skips a download when the destination
  exists, so caching `temp/` between runs turns a slow job into a fast one.
- **Models that need a GPU to convert.** Move that model to its own
  `dep_group` and give the matrix entry a self-hosted `runs-on`.
- **A model too slow for every PR.** Drop a `.skip` file to take it out of all
  matrices, or split it into a separate scheduled workflow.
- **Publishing somewhere other than GitHub releases.** Only the publish jobs
  are GitHub-specific; `discover` and `build` are just `dtai` commands and
  port to any CI system.

---

## Related

- [`building-a-repo.md`](building-a-repo.md) – the full walkthrough, from
  scaffold to shipped package
- [`dtmodel-format.md`](dtmodel-format.md) – the archive format and how
  darktable installs and updates a model
- [`model-yaml-spec.md`](model-yaml-spec.md) – `version`, `dep_group` and
  every other field these workflows read
