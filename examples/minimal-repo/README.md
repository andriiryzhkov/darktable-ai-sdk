# minimal-repo

The smallest model repository that actually builds a `.dtmodel`.

It contains one model, `identity`, whose conversion script constructs a 1-node
ONNX graph that returns its input unchanged. No weights are downloaded, no
submodules are vendored, and the whole pipeline runs in a second – which makes
it useful for checking that a toolchain works before pointing it at a real
model.

## Try it

```bash
cd examples/minimal-repo
uv sync                   # brings in the SDK, onnx and onnxruntime
uv run dtai run identity
```

The install is for `onnx` and `onnxruntime`, which the conversion and
validation steps need – `dtai` itself comes from the SDK and finds this repo
by walking up from the current directory.

`dtai run` chains the four stages:

| Stage | What happens here |
|---|---|
| setup | nothing – no checkpoints, no submodule |
| convert | `models/identity/convert.py` writes `output/identity/model.onnx`, then the SDK writes `output/identity/config.json` from `model.yaml` |
| validate | loads the ONNX with onnxruntime, prints its inputs/outputs, checks `config.json` has the required keys |
| package | zips `output/identity/` into `output/identity.dtmodel` |

Individual stages work too: `dtai convert identity`, `dtai validate`,
`dtai package`. Omit the model id to run over every model in the repo.

`dtai list` shows what the repo offers. `dtai info` is a *repo-local* command
living alongside the SDK's built-ins – it reports what this repository holds
and how much of it has been built:

```console
$ dtai info

minimal-repo
  root         /path/to/examples/minimal-repo
  models       1
  tasks        denoise (1)
  dep groups   core (1)

Models:
  identity  denoise    v1.0    packaged, 839 B
```

The last column tracks build state per model – `not built`, `converted, not
packaged`, or `packaged` with the archive size. It's defined in
[`minimal_repo/cli.py`](minimal_repo/cli.py) and reaches `dtai` through the
`[tool.dtai] extend` key in [`pyproject.toml`](pyproject.toml); the repo
never declares a `dtai` script of its own.

## What to look at

| File | Why |
|---|---|
| [`models/identity/model.yaml`](models/identity/model.yaml) | The schema, annotated – including commented-out `checkpoints:` and `repo:` blocks showing what a real model adds |
| [`models/identity/convert.py`](models/identity/convert.py) | The conversion-script contract: a module-level `convert(**args)` |
| [`minimal_repo/cli.py`](minimal_repo/cli.py) | How a repo adds its own command (`info`) to the SDK's `dtai` – the only code a repo ever needs |
| [`pyproject.toml`](pyproject.toml) | Where model dependencies live – note that `onnx` is the *repo's* dependency, not the SDK's |

## Inspecting the result

```bash
unzip -l output/identity.dtmodel
#   identity/config.json
#   identity/model.onnx

cat output/identity/config.json
```

That archive is installable: darktable's preferences has an *install from file*
action that takes a `.dtmodel`. The `identity` model claims the `denoise` task,
so installing it will offer it as a denoiser – it will do nothing to your
image, which is the point.

## Starting your own

Don't copy this directory – scaffold instead, which gets you a `.gitignore`,
a `samples/` and `vendor/` layout, and correct naming:

```bash
uvx --from darktable-ai-sdk dtai init ./my-models --name my-models
```

Then read [`docs/building-a-repo.md`](../../docs/building-a-repo.md).
