# `model.yaml` specification

Every model in a repository lives in its own directory under `models/` and is
described by a single `model.yaml`:

```text
models/
  denoise-nafnet/
    model.yaml        <- this file
    convert.py        <- conversion script(s) it references
```

`model.yaml` is the **input** contract: it tells the SDK how to fetch weights,
how to convert them, and what metadata to bake into the package. The
**output** contract – what darktable actually reads – is `config.json` inside
the `.dtmodel` archive, described in [`dtmodel-format.md`](dtmodel-format.md).
The two overlap but are not identical; the mapping is spelled out at the end of
this document.

The file is loaded by `dt_ai_sdk.config.load_model_config`. Parsing is
deliberately thin: unknown keys are ignored, and a missing required key raises
`KeyError` rather than a schema error. Validate your repo by running
`dtai list` – it loads every `model.yaml` and will surface a failure straight
away.

---

## Required fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique within the repo. **Must equal the model's directory name** – the CLI resolves `dtai convert <id>` to `models/<id>/`, and darktable rejects an archive whose top-level directory doesn't match. Keep it to characters valid in a path segment: no `/`, `\`, `.` or `..`. |
| `name` | string | Short human-readable name, shown in darktable's UI. |
| `description` | string | One-line summary, shown in darktable's model list. |
| `task` | string | What the model does. darktable groups models by task and activates one model per task. Values used by the reference repo: `denoise`, `rawdenoise`, `upscale`, `mask`, `person`. |

A minimal valid file:

```yaml
id: my-model
name: My Model
description: Does a useful thing
task: denoise
```

That alone is enough for `dtai list`, `dtai convert` (which emits
`config.json` and nothing else), and `dtai package`.

---

## Optional fields

### Model shape and behaviour

| Field | Type | Default | Notes |
|---|---|---|---|
| `type` | `single` \| `split` \| `multi` | `single` | Determines what `dtai validate` expects in the output directory – see [Output layout by type](#output-layout-by-type). It does **not** appear in `config.json`. |
| `version` | string | `"1.0"` | Model version, copied into `config.json`. Quote it – bare `1.0` parses as a float and would serialise as `1.0` rather than `"1.0"`. darktable compares this string to decide whether an update is available. |
| `arch` | string | `"generic"` | Architecture tag (`nafnet`, `unet`, `sam2`, …). Copied into `config.json`; informational. |
| `tiling` | bool | `false` | Declares that the model is safe to run tile-by-tile on large images. Copied into `config.json`. |
| `dep_group` | string | `"core"` | Names the dependency group this model needs. The SDK never installs anything itself; it just passes the value to the repo's dep-sync hook and emits it in `dtai list --json-output` for CI matrices. |

### Metadata

| Field | Type | Default | Notes |
|---|---|---|---|
| `model_card` | map of string→string | `{}` | Provenance and licensing. Copied verbatim into `config.json` under `model_card` and rendered in darktable's model info panel. See [Model card fields](#model-card-fields). |
| `attributes` | free-form map | `{}` | Runtime hints for the inference backend. Copied verbatim into `config.json`. See [Attributes](#attributes). |
| `cpu_only` | list or map | omitted | Declares that the model (or named parts of it) must run on CPU. Copied into `config.json` only when present. |
| `coreml_format` | string or map | omitted | Core ML conversion target, e.g. `mlprogram`. Copied into `config.json` only when present. |

### Sources and build steps

| Field | Type | Default | Notes |
|---|---|---|---|
| `repo` | map | omitted | An upstream project needed at conversion time, vendored as a git submodule. See [`repo`](#repo). |
| `checkpoints` | list of maps | `[]` | Weights to download before converting. See [`checkpoints`](#checkpoints). |
| `convert` | list of maps | `[]` | Conversion steps. See [`convert`](#convert). |
| `demo` | map | `{}` | Per-image arguments for a repo-specific demo command. Parsed by the SDK but never used by it – provided so downstream `demo` commands have a standard place to read from. |

### Fields that are *not* read

- **`backend`** – the reference repo's `model.yaml` files carry `backend: onnx`,
  but the SDK ignores it. `config.json` always gets `"backend": "onnx"`. The key
  is harmless to include and is reserved for when a second backend appears.
- **`skip`** – not a YAML field. A model is skipped when a file named `.skip`
  exists in its directory. `dtai list` marks it `(skipped)`, and
  `dtai convert` / `validate` / `package` / `run` pass over it when run without
  an explicit model id. Naming the model explicitly still processes it.

---

## `repo`

Some conversions need upstream code (model class definitions, config files) that
isn't on PyPI. Vendor it as a git submodule and declare it:

```yaml
repo:
  submodule: vendor/NAFNet          # path relative to repo root
  setup: pip install -r requirements.txt   # optional, run inside the submodule
```

| Key | Required | Notes |
|---|---|---|
| `submodule` | yes | Path relative to the repo root. `dtai setup` runs `git submodule update --init <submodule>` if the directory is missing. |
| `setup` | no | Shell command run **inside** the submodule directory after init, with `DTAI_ROOT` set to the repo root in the environment. Runs through the shell, so pipes and `&&` work. |

At conversion time the SDK prepends the submodule directory **and** its `src/`
subdirectory to `sys.path`, so conversion scripts can `import` upstream modules
directly.

---

## `checkpoints`

```yaml
checkpoints:
  - url: "https://github.com/cszn/KAIR/releases/download/v1.0/BSRGAN.pth"
    path: "temp/upscale-bsrgan/BSRGAN.pth"
  - url: "gdrive://1qkXIvxnlY3Z4xLYGWJcoAHBUNyDmvwPS"
    path: "temp/mask-object-segnext-b2hq/vitb_sa2_hq44k.pth"
```

Both keys are required.

- **`url`** – plain HTTP(S) URLs are fetched with `curl -L`. Google Drive is
  recognised in three forms and rewritten to the direct-download endpoint:
  `gdrive://<file-id>`, any URL containing `/file/d/<file-id>`, and any URL with
  an `id=<file-id>` query parameter.
- **`path`** – destination, **relative to the repo root** (not to the model
  directory). Parent directories are created. Convention is
  `temp/<model-id>/<filename>` for intermediate weights; use
  `output/<model-id>/<filename>` when the download *is* the final artefact and
  no conversion step is needed.

Downloads are skipped when the destination already exists, so `dtai setup` is
cheap to re-run. There is **no checksum verification** – the SDK does not
support a `sha256` key on checkpoints. Integrity checking happens downstream, on
the published `.dtmodel` asset (see [`dtmodel-format.md`](dtmodel-format.md)).

---

## `convert`

Each step names a Python script and the keyword arguments to call it with:

```yaml
convert:
  - script: convert.py
    args:
      checkpoint: "{temp}/BSRGAN.pth"
      output: "{output}/model_x4.onnx"
      scale: 4
      opset: 20
      static: true
```

- **`script`** – path relative to the **model directory**. `../other-model/convert.py`
  is a valid and commonly used way to share one script between model variants.
- **`args`** – passed as keyword arguments. String values get template variables
  substituted; non-strings (ints, floats, bools, lists) pass through untouched.

The script is imported as a module and must expose a top-level `convert`
function accepting those keywords:

```python
def convert(checkpoint: str, output: str, scale: int,
            opset: int = 20, static: bool = False) -> None:
    ...
```

Steps run in listed order, in-process – a failing step raises and aborts the
run. Multiple steps are how a `multi` model produces several ONNX files
(see the BSRGAN example: one step per scale factor).

A model with no `convert` block is legal. `dtai convert` then only emits
`config.json`, which is exactly what you want when the checkpoint you downloaded
is already an ONNX file placed directly in `output/<id>/`.

### Template variables

Available in any string value inside `args`:

| Variable | Expands to |
|---|---|
| `{root}` | Repo root |
| `{model_dir}` | `<root>/models/<id>` |
| `{temp}` | `<root>/temp/<id>` |
| `{output}` | `<root>/output/<id>` |
| `{repo}` | `<root>/<repo.submodule>`, or an empty string when no `repo` is declared |

Substitution uses `str.format`, so a literal brace in an argument value must be
doubled (`{{`, `}}`).

---

## Output layout by type

`dtai convert` creates `output/<id>/` and the conversion steps are expected to
write their artefacts there. `dtai validate` then checks the layout according to
`type`:

| `type` | Expected in `output/<id>/` |
|---|---|
| `single` (default) | `config.json` + `model.onnx` |
| `split` | `config.json` + `encoder.onnx` + `decoder.onnx` |
| `multi` | `config.json` + at least one `*.onnx`, any names |

Validation loads each ONNX file with `onnxruntime` on the CPU provider and
prints the input/output tensor names, shapes and dtypes. It exits non-zero if a
file is missing, fails to load, or if `config.json` lacks any of `id`, `name`,
`description`, `task`, `backend`, `version`.

`onnxruntime` is **not** an SDK dependency – `dtai validate` imports it lazily,
so add it to your repo's dependencies if you want validation to run.

---

## Model card fields

All are optional strings; darktable renders whichever are present. Using the
established key names matters – darktable looks them up individually:

| Key | Content |
|---|---|
| `long_description` | Several sentences: what it does, when to reach for it, known weaknesses. |
| `scope` | The task in a few words, e.g. `"single-image denoising"`. |
| `author` | Original authors / lab. |
| `source` | Upstream repository URL. |
| `paper` | Paper URL. |
| `license` | License of the **weights and code**, e.g. `Apache-2.0`. |
| `training_data` | What the model was trained on, with dataset sizes. |
| `training_data_license` | Licensing of that data – often different from, and more restrictive than, the model license. |
| `notes` | Caveats: research-only datasets, unclear provenance, output quirks. |

The last three exist because a permissively-licensed model is frequently trained
on data that isn't. Filling them in honestly is the point of the card – users
deciding whether they may use a model in commercial work depend on it.

---

## Attributes

`attributes` is a free-form map copied verbatim into `config.json`, where
darktable reads individual keys through its typed attribute accessors (bool,
int, double, string, int-array). Nothing here is validated by the SDK – a
misspelled key is silently ignored at runtime, so check against the values the
consuming code actually looks up.

Keys the reference repo sets, and what reads them:

| Key | Type | Meaning |
|---|---|---|
| `input_sizes` | list of int | Fixed input dimensions the ONNX graph was exported at. darktable's restore pipeline uses the first entry as its tile size. |
| `shadow_boost` | bool | Opt-in flag: the model hallucinates in dark patches, so darktable pre-boosts shadows before inference. |
| `resize_mode` | string | e.g. `longest_side` – how to fit the image to the input size. |
| `size_multiple` | int | Round both dimensions up to a multiple of this. |
| `color_space` | string | e.g. `rgb`. |
| `norm_mean` / `norm_std` | list of float | Per-channel normalisation applied before inference. |
| `output_kind` | string | e.g. `alpha_matte` – how to interpret the raw output. |
| `output_activation` | string | e.g. `none` – activation still to be applied, if any. |

For a `multi` model, per-file attributes nest under the ONNX file's stem, and
darktable falls back to the top level when the nested key is absent:

```yaml
attributes:
  model_x2:
    input_sizes: [512]     # looked up as "model_x2.input_sizes"
  model_x4:
    input_sizes: [256]     # looked up as "model_x4.input_sizes"
```

---

## Mapping to `config.json`

`dtai convert` writes `output/<id>/config.json` from `model.yaml`:

| `config.json` key | Source |
|---|---|
| `id`, `name`, `description`, `task`, `arch`, `version`, `tiling` | copied from `model.yaml` |
| `backend` | always the literal `"onnx"` |
| `model_card`, `attributes` | copied, **omitted when empty** |
| `cpu_only`, `coreml_format` | copied, **omitted when absent** |

Everything else in `model.yaml` (`type`, `dep_group`, `repo`, `checkpoints`,
`convert`, `demo`) is build-time only and does not ship in the package.

> **Gap worth knowing about:** darktable also reads a `spatial_dims` key from
> `config.json` – a two-element array naming the symbolic height and width
> dimensions of the ONNX graph, defaulting to `"height"` / `"width"` when
> absent. There is currently no `model.yaml` field for it, so `dtai convert`
> never emits it. Models whose exported graph uses different symbolic dimension
> names need it written into `config.json` by other means until the schema gains
> a field.

---

## Complete example

```yaml
id: denoise-nafnet
name: "denoise nafnet small"
description: "NAFNet denoiser trained on SIDD dataset"
task: denoise
version: "1.0"
arch: nafnet
type: single
tiling: true
dep_group: nafnet
coreml_format: mlprogram

attributes:
  input_sizes: [768]
  shadow_boost: true

model_card:
  long_description: "NAFNet (Nonlinear Activation Free Network) lightweight denoiser trained on the SIDD smartphone denoising dataset"
  scope: "single-image denoising"
  author: "Megvii Research"
  source: "https://github.com/megvii-research/NAFNet"
  paper: "https://arxiv.org/abs/2204.04676"
  license: "MIT"
  training_data: "SIDD – 30K real smartphone noisy/clean pairs captured by authors (5 devices)"
  training_data_license: "MIT"
  notes: "all components publicly available under permissive licenses"

repo:
  submodule: vendor/NAFNet

checkpoints:
  - url: "https://drive.google.com/file/d/1lsByk21Xw-6aW7epCwOQxvm6HYCQZPHZ/view"
    path: "temp/denoise-nafnet/NAFNet-SIDD-width32.pth"

convert:
  - script: convert.py
    args:
      config: "{repo}/options/test/SIDD/NAFNet-width32.yml"
      checkpoint: "{temp}/NAFNet-SIDD-width32.pth"
      output: "{output}/model.onnx"
      opset: 20
      height: 768
      width: 768
      static: true
      fp16: false
```
