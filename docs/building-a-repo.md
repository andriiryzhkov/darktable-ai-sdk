# Building a model repository

How to go from "I have a model" to "a darktable user can install it".

A model repository is an ordinary Python package that declares its models in
YAML and provides a script per model that exports ONNX. The SDK supplies the
`dtai` command that drives the build; you supply the models.

What you get out of it is a package that provably matches the format darktable
reads – built to the schema, validated against a real ONNX runtime. How it then
reaches users is a separate matter, and worth reading before you plan around
it: [Ship it](#7-ship-it).

**Prerequisites:** Python 3.11+, and whatever your model's export needs
(usually `torch` and `onnx`).

---

## 1. Scaffold

```bash
# one-shot with uv, no install needed:
uvx --from darktable-ai-sdk dtai init ./my-models --name my-models

# or install the SDK first:
pip install darktable-ai-sdk
dtai init ./my-models --name my-models
```

You get:

```text
my-models/
├── pyproject.toml          # depends on the SDK
├── README.md
├── .gitignore              # ignores output/, temp/, *.dtmodel, vendor checkouts
├── my_models/
│   ├── __init__.py
│   └── cli.py              # optional CLI extensions, inert until enabled
├── models/example/
│   └── model.yaml          # annotated starting point
├── samples/README.md       # test images live here
└── vendor/README.md        # git submodules live here
```

`init` refuses to overwrite existing files unless you pass `--force`, so it's
safe to run into a directory that already has a `README` or a `.git`.

Install it and work inside its environment:

```bash
cd my-models
uv sync                    # or: python -m venv .venv && pip install -e .
source .venv/bin/activate
dtai list
```

`dtai` comes from the SDK and finds the repo by walking up from the current
directory – there is no per-repo wiring. But **which** `dtai` you get depends
on the environment, and that distinction matters as soon as a command needs
one of your model's dependencies:

| How you invoke it | Sees repo dependencies? |
|---|---|
| venv activated, then `dtai …` | yes – the recommended way |
| `uv run dtai …` (no activation) | yes – same environment, one prefix |
| `uv tool install darktable-ai-sdk`, then `dtai …` | **no** – deliberately isolated |

The third is a standalone SDK install. It's handy for `dtai init` before a
repo exists, but it can't see anything your repo declares, so `dtai validate`
there fails on a missing `onnxruntime` no matter what your repo lists. Use
`uv tool install darktable-ai-sdk --with onnxruntime` if you want a global
`dtai` that can at least validate, and reach for the repo environment for
anything involving a real conversion.

The trap is having both: with the venv inactive, a global `dtai` silently
takes over and fails on dependencies you know you installed. Activating the
venv puts `.venv/bin` first on `PATH`, which settles it.

## 2. Describe a model

Rename `models/example/` to your model's id and edit its `model.yaml`. The
directory name and the `id` field must match – the CLI resolves
`dtai convert <id>` to `models/<id>/`, and darktable rejects an archive whose
top-level directory disagrees with its id.

The four required fields:

```yaml
id: my-denoiser
name: "my denoiser"
description: "UNet denoiser trained on my dataset"
task: denoise
```

`task` decides which darktable feature can use the model. The reference repo
uses `denoise`, `rawdenoise`, `upscale`, `mask` and `person`; a task darktable
doesn't know about will build fine and simply won't be offered anywhere.

Add the weights to fetch and the conversion step to run:

```yaml
version: "1.0"
arch: unet
tiling: true

checkpoints:
  - url: "https://example.com/weights.pth"
    path: "temp/my-denoiser/weights.pth"

convert:
  - script: convert.py
    args:
      checkpoint: "{temp}/weights.pth"
      output: "{output}/model.onnx"
      opset: 20
```

Then fill in `model_card` – provenance, licence, what the model was trained on
and under what terms. darktable renders it in the model info panel, and it's
what a user consults before deciding whether they may use your model in paid
work. `training_data_license` is frequently more restrictive than the model's
own licence; say so when it is.

Every field, and everything omitted here, is in
[`model-yaml-spec.md`](model-yaml-spec.md).

## 3. Write the conversion script

`models/<id>/convert.py` is a plain module with a top-level `convert` function.
The SDK imports it and calls `convert(**args)` with the `args` map from
`model.yaml`, after substituting `{output}`, `{temp}`, `{repo}` and friends into
string values:

```python
def convert(checkpoint: str, output: str, opset: int = 20) -> None:
    import torch
    from pathlib import Path

    Path(output).parent.mkdir(parents=True, exist_ok=True)

    model = MyNet()
    model.load_state_dict(torch.load(checkpoint, map_location="cpu"))
    model.eval()

    dummy = torch.randn(1, 3, 512, 512)
    torch.onnx.export(
        model, dummy, output, opset_version=opset,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input":  {0: "batch", 2: "height", 3: "width"},
                      "output": {0: "batch", 2: "height", 3: "width"}},
    )
```

Two things to get right:

- **Write into the output directory.** `{output}` expands to
  `<repo-root>/output/<id>/`, and everything there ends up in the package.
  Scratch files belong in `{temp}`.
- **Name the dynamic axes `height` and `width`.** Those are the names darktable
  assumes. Other names require a `spatial_dims` key in `config.json`, which the
  SDK cannot currently emit (see the gap note in
  [`dtmodel-format.md`](dtmodel-format.md#configjson)).

A model needing upstream code that isn't on PyPI vendors it as a submodule:

```yaml
repo:
  submodule: vendor/upstream-project
  setup: pip install -r requirements.txt
```

`dtai setup` initialises the submodule and runs `setup` inside it, and at
conversion time the submodule and its `src/` are prepended to `sys.path` – so
your script can `import` upstream modules directly.

If your "conversion" is just downloading an ONNX file someone already exported,
skip `convert` entirely and point the checkpoint at the output directory:

```yaml
checkpoints:
  - url: "https://huggingface.co/…/model.onnx"
    path: "output/my-model/model.onnx"
```

`dtai convert` will then only emit `config.json`, which is all that's left to do.

## 4. Build

```bash
dtai run my-denoiser
```

which chains the four stages, each also available on its own:

| Command | Does |
|---|---|
| `dtai setup <id>` | init submodules, run repo setup, download checkpoints (skips ones already present) |
| `dtai convert <id>` | run the conversion steps, write `output/<id>/config.json` |
| `dtai validate <id>` | load each ONNX with onnxruntime, print its I/O, check `config.json`'s required keys |
| `dtai package <id>` | zip `output/<id>/` into `output/<id>.dtmodel` |

Omit the id to process every model that isn't marked skipped. To park a model
that isn't ready, drop an empty `.skip` file in its directory – `dtai list`
will show it as `(skipped)` and bulk commands will pass over it, while naming it
explicitly still works.

`dtai validate` imports `onnxruntime` lazily; add it to your repo's
dependencies if you want validation to run.

## 5. Handle differing dependencies

Models that need conflicting dependency sets – one on torch 2.2, another on
mmcv – can't share one environment. Tag each model with a `dep_group`:

```yaml
dep_group: my-denoiser
```

declare the group in `pyproject.toml`:

```toml
[dependency-groups]
my-denoiser = ["torch>=2.2", "onnx>=1.16"]
```

and register a hook in your `cli.py` (see step 6 for enabling it), which the SDK
calls once per model before convert and validate:

```python
import subprocess
from dt_ai_sdk.cli import set_sync_deps_hook

set_sync_deps_hook(lambda cfg: subprocess.run(
    ["uv", "sync", "--group", cfg.dep_group],
    cwd=str(cfg.root_dir), check=True,
))
```

The SDK never assumes a package manager – the hook is where uv, pip or poetry
gets named. `dtai list --json-output` emits `[{"id":…, "dep_group":…}]`, which
is designed to feed a CI build matrix so each group gets its own job.

## 6. Add repo-specific commands

Everything so far needed no code from your repo. Two things do: the dep-sync
hook above, and commands the SDK can't know about. Both live in `cli.py`, which
registers onto the SDK's group:

```python
import click
from dt_ai_sdk.__main__ import main

@main.command("demo")
@click.argument("model_id")
@click.pass_context
def demo_cmd(ctx, model_id):
    """Run the model over samples/ and write comparison images."""
    ...
```

Point `dtai` at the module in `pyproject.toml` and install the repo:

```toml
[tool.dtai]
extend = "my_models.cli"
```

`dtai` imports it on first command lookup, so `dtai demo` and the built-in
commands sit in one CLI.

**Don't declare a `dtai` console script of your own.** Two packages installing
a script of the same name collide in the environment's `bin/`, and the winner
is decided by install order – which is exactly the failure this mechanism
exists to avoid.

The reference repo adds `demo`, `eval` and `versions` this way. If you need to
iterate over models the same way the built-in commands do, the helpers are
public:

```python
from dt_ai_sdk.cli import get_root, iter_selected_models, load_or_fail
```

`model.yaml`'s `demo.image_args` block exists for exactly this: the SDK parses
it and does nothing with it, leaving a standard place for your demo command to
read per-image arguments from.

## 7. Ship it

`output/<id>.dtmodel` is the deliverable. A user installs it through darktable's
preferences – there's an *install from file* action that takes a `.dtmodel` –
and the model is first-class from then on.

Publishing for automatic download is more involved, and worth understanding
before you plan for it: the **catalogue** of downloadable models is bundled
inside darktable itself, not read from your repository. Pointing darktable's
`plugins/ai/repository` setting at your GitHub repo changes where assets are
*fetched from*, but the list of model ids on offer still comes from darktable's
own `ai_models.json`. So:

- **Install-from-file** works for any model, needs no coordination, and is the
  path to plan around for a new model.
- **Repository redirect** lets you serve substitute builds for ids darktable
  already lists. It requires publishing `releases-index.json` and
  `versions.json` alongside your release assets – formats documented in
  [`dtmodel-format.md`](dtmodel-format.md#distribution). `dtai versions`
  generates the second, and the scaffolded CI calls it on a release tag; the
  first is a small file you maintain by hand.
- Getting a genuinely **new** id into the built-in catalogue is a change to
  darktable's `data/ai_models.json`, on darktable's release cycle.

Whichever path, bump `version` in `model.yaml` on every republish. A changed
archive under an unchanged version leaves users on stale weights with no signal
that anything moved.

The scaffolded CI does the mechanical parts: `.github/workflows/release.yml`
builds every model on a `release-*` tag and attaches the archives plus
`versions.json` to a draft release, and `nightly.yml` rolls a pre-release
whenever a model definition lands on the default branch. Repo-level versions
come from `dtai git-version`, which reads your `release-*` tags:

```bash
dtai git-version            # 5.6.0, or 5.6.0+47~gabc1234 past the tag
dtai git-version --prefix   # 5.6.0 – the key a release channel is named for
```

Both fall back gracefully: no tags yet means a bare commit hash and an empty
prefix, which is why a fresh repo's nightly rolls a single `nightly` tag until
its first release.

[`ci-and-releasing.md`](ci-and-releasing.md) covers all three workflows in
detail, the two index files, and what a fresh repo needs before its first
green run.

---

## Running `dtai` on a repository you didn't write

A model repository is code, not data, and `dtai` executes it. That is what
makes the format work – a conversion is an arbitrary Python script, because
exporting a model is an arbitrary problem – but it means **cloning someone
else's model repo and running `dtai` in it runs their code as you**.

Three paths execute repository-supplied code:

| What | When | Declared in |
|---|---|---|
| The CLI extension module | any `dtai` command, on first command lookup | `[tool.dtai] extend` in `pyproject.toml` |
| The `repo.setup` command, via the shell | `dtai setup` | `repo: setup:` in `model.yaml` |
| Each conversion script | `dtai convert` | `convert: script:` in `model.yaml` |

The first is the one that surprises people: the extension is imported before
any command runs, so even `dtai list` – which looks like it only reads YAML –
executes the repo's `cli.py` if one is declared. There is no read-only mode.

`dtai setup` additionally initialises git submodules and downloads whatever
`checkpoints:` names, which are network fetches from URLs the repo chooses.
Checkpoints are **not** checksum-verified (see
[`checkpoints`](model-yaml-spec.md#checkpoints)), so a compromised or
redirected download is not detected at this stage.

None of this is unusual – it is the same trust you extend to `make`, `npm
install`, or any `pyproject.toml` with a build backend. Treat it the same way:

- **Read `model.yaml`, `cli.py` and the conversion scripts** before running
  `dtai` in a repo you don't control. They're small and plain text.
- **Prefer a container or throwaway VM** for anything you haven't reviewed.
- **In CI, remember the workflows run on your runners with your token.** The
  scaffolded `check-pr.yml` declares `contents: read` and holds no secrets for
  exactly this reason; the publish workflows need `contents: write`, so be
  deliberate about running them on branches from forks.

Consuming a **built** `.dtmodel` is a different and much narrower matter: it's
a zip of ONNX plus JSON, darktable validates the archive's structure on
install, and nothing in it executes as code.

## Using the SDK as a library

`dtai` is a convenience, not a requirement. Every stage is a plain function:

```python
from pathlib import Path
from dt_ai_sdk import (
    discover_models, download_checkpoints,
    run_conversion, package_model, run_validation,
)

root = Path("/path/to/my-models")
for cfg in discover_models(root):
    if cfg.skip:
        continue
    download_checkpoints(cfg.checkpoints, root)
    run_conversion(cfg)
    run_validation(cfg)
    package_model(cfg)
```

Which is useful when the build is driven by something that isn't a CLI – a
CI script, a notebook, a larger training pipeline.

---

## Reference

- [`examples/minimal-repo/`](../examples/minimal-repo/) – a complete repo that
  builds a real `.dtmodel` in about a second, with no weights to download
- [`model-yaml-spec.md`](model-yaml-spec.md) – every field
- [`dtmodel-format.md`](dtmodel-format.md) – the archive format and how
  darktable installs it
- [darktable-ai](https://github.com/darktable-org/darktable-ai) – the reference
  repository, with a dozen real models
