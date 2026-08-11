# Darktable AI SDK

Build and publish model repositories that darktable installs as `.dtmodel`
packages. Describe each model in a `model.yaml`; the SDK fetches its weights,
runs your conversion script, validates the ONNX and packages the result.

What the SDK guarantees is compatibility: a package it builds and validates
matches the format darktable reads.

## Install

```bash
pip install darktable-ai-sdk
```

The SDK's own dependencies are minimal (`click`, `pyyaml`). Model-specific
converters bring their own dependencies (`torch`, `onnx`, etc.) in the model
repository – the SDK just orchestrates.

## What it gives you

- `ModelConfig` / `load_model_config` – the authoritative `model.yaml` schema
- `discover_models` – find every model in a repo
- `download_checkpoints` – pull source checkpoints from HTTP / Google Drive
- `run_conversion` – invoke a model's declared conversion scripts and emit `config.json`
- `package_model` – zip the produced output as a `.dtmodel` archive
- `run_validation` / `validate_onnx` / `validate_config_json` – check a produced package

## Minimal usage

```python
from pathlib import Path
from dt_ai_sdk import discover_models, run_conversion, package_model

root = Path("/path/to/your/model-repo")
for cfg in discover_models(root):
    if cfg.skip:
        continue
    run_conversion(cfg)
    package_model(cfg)
```

## Starting a new model repo

```bash
# one-shot with uv, no install required:
uvx --from darktable-ai-sdk dtai init ./my-models --name my-models

# or install once, then run:
pip install darktable-ai-sdk
dtai init ./my-models --name my-models

cd my-models
dtai list               # works immediately – dtai finds the repo from the cwd
```

`dtai init` scaffolds `pyproject.toml`, `models/example/`, `samples/`,
`vendor/`, and the usual Python + git ignore boilerplate.

`dtai` is the SDK's and carries every command – `init`, `setup`, `convert`,
`validate`, `package`, `list`, `run`. It locates a repository by walking up
from the current directory, so a model repo needs no CLI code of its own. A
repo that wants extra commands or a dependency-sync hook writes them in a
module and names it in `pyproject.toml`:

```toml
[tool.dtai]
extend = "my_models.cli"
```

which `dtai` imports on first command lookup. Repos should not declare a
`dtai` console script – two packages owning the same script name collide,
and install order picks the winner.

## Documentation

[`docs/`](docs/) is the index; it routes by task and lists what each document
answers.

- [`docs/building-a-repo.md`](docs/building-a-repo.md) – step-by-step, from
  scaffold to shipped `.dtmodel`
- [`docs/model-yaml-spec.md`](docs/model-yaml-spec.md) – every `model.yaml`
  field, and how it maps into the package
- [`docs/ci-and-releasing.md`](docs/ci-and-releasing.md) – the GitHub Actions
  workflows a scaffolded repo ships, and how to cut a release
- [`docs/dtmodel-format.md`](docs/dtmodel-format.md) – the archive format,
  `config.json`, and how darktable installs and updates a model

[`examples/minimal-repo/`](examples/minimal-repo/) is a complete repository
that builds a real `.dtmodel` in about a second with no weights to download –
useful for checking a toolchain before pointing it at a real model. For a
dozen real models, see
[darktable-ai](https://github.com/darktable-org/darktable-ai).

## Development

```bash
uv sync --extra dev      # or: pip install -e .[dev]
uv run pytest
```

The `dev` extra pulls `onnx` and `onnxruntime` as well as pytest. Without
them the example-repo tests silently skip rather than fail, so a full local
run needs the extra.

### Continuous integration

Two workflows, both in `.github/workflows/`.

**`test.yml`** – on every push and pull request:

- `pytest` on Python 3.11–3.14, plus one Windows job. The scaffolder builds
  paths and renames files (`github/` → `.github/`, `gitignore` →
  `.gitignore`), which is the part most likely to behave differently there.
- a separate `build` job that runs `uv build`, `twine check`, then installs
  the built wheel and **actually scaffolds a repo from it**, asserting the
  workflows, example model and `releases-index.json` all arrived.

That last check exists because the unit tests import templates from the
source tree, so they pass even if packaging drops them. A wheel that builds
but ships no templates would produce empty repos, and nothing else would
notice.

**`publish.yml`** – described under [Releasing](#releasing).

## Releasing

The version lives in exactly one place – `__version__` in
`dt_ai_sdk/__init__.py`. `pyproject.toml` reads it via
`[tool.hatch.version]`, so there is nothing else to bump. It is also what
`dtai init` pins into every scaffolded repo's dependency on the SDK, which
is why a stale copy would be worse than cosmetic.

```bash
# 1. bump __version__ in dt_ai_sdk/__init__.py, commit
# 2. dry run to TestPyPI (repeatable):
#      Actions -> Publish -> Run workflow -> target: testpypi
# 3. release:
git tag v0.2.0 && git push origin v0.2.0
```

### How the publish workflow runs

It has exactly two triggers, so an ordinary commit can never publish:

| Invocation | Publishes to |
|---|---|
| push a `v*` tag | PyPI |
| *Actions → Publish → Run workflow*, `target: testpypi` | TestPyPI |
| *Actions → Publish → Run workflow*, `target: pypi` | PyPI |

Every run starts with the same `build` job, which gates the rest: it reads
`__version__`, **fails if a tag disagrees with it**, runs the tests, builds,
and `twine check`s the result. Only then does one publish job upload the
artifact.

The tag check matters more than it looks. PyPI never lets a version be
replaced, so a mismatched tag would burn that number permanently – and
because `__version__` is what gets pinned into scaffolded repos, it would
also ship wrong pins to anyone who scaffolded from that release.

The publish jobs declare `environment: pypi` / `testpypi`. Those environments
must exist for the jobs to run at all, and a required reviewer on `pypi` makes
the run pause after building and wait for your approval before uploading.

### One-time PyPI setup

Publishing uses **Trusted Publishing** (OIDC): PyPI is told to trust this
exact workflow in this exact repository, and no API token is stored here.

On <https://pypi.org/manage/account/publishing/>, add a *pending
publisher* (the project does not exist yet, which is what "pending"
means):

| Field | Value |
|---|---|
| PyPI project name | `darktable-ai-sdk` |
| Owner | `andriiryzhkov` |
| Repository name | `darktable-ai-sdk` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Repeat on <https://test.pypi.org/manage/account/publishing/> with
environment `testpypi` for the dry-run path.

Then in the GitHub repo, create environments named `pypi` and `testpypi`
(*Settings → Environments*). They are what the workflow's `environment:`
keys refer to, and adding a required reviewer to `pypi` makes every real
upload need an explicit approval.
