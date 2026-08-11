# The `.dtmodel` package format

A `.dtmodel` file is the unit darktable installs. It is a plain zip archive
containing one model: its ONNX weights and a `config.json` describing them.

This document is the format contract – what a producer must emit and what
darktable guarantees to read.

---

## Archive layout

```text
upscale-bsrgan.dtmodel          (zip, DEFLATE)
└── upscale-bsrgan/             <- single top-level directory, named for the model id
    ├── config.json             <- required
    ├── model_x2.onnx
    └── model_x4.onnx
```

Rules, all of them load-bearing:

1. **The archive filename is `<model-id>.dtmodel`.** darktable derives download
   URLs and asset names from the id, so the two must agree.
2. **There is exactly one top-level directory, and its name is the model id.**
   On install darktable reads the top-level directory name out of the *first*
   zip entry and uses it as the model id. If that directory doesn't match, the
   install is rejected.
3. **The id must be a safe path segment.** darktable refuses an id that is
   empty, `.`, `..`, or contains `/` or `\` – it becomes both a directory name
   and a config key.
4. **`config.json` sits directly inside that directory.** Not at the archive
   root, not nested deeper.
5. **Entry paths use `/`** as the separator (standard zip; Python's `zipfile`
   does this for you).

`package_model` emits exactly this. It walks `output/<id>/` recursively in
sorted order and writes each file as `<id>/<relative-path>`, so subdirectories
are preserved if your conversion produces them.

Nothing else is prescribed. Extra files – a `LICENSE`, a `README`, auxiliary
`.json` – travel with the package and are ignored by darktable. Empty
directories are not stored, since only files are written.

### What the layout should contain

`dtai validate` enforces a convention matching the model's declared `type`:

| `type` | Files |
|---|---|
| `single` | `model.onnx` |
| `split` | `encoder.onnx`, `decoder.onnx` |
| `multi` | one or more `*.onnx`, any names |

This is the SDK's convention, not something darktable's loader hard-codes – but
the reference models follow it and darktable's per-task loading code is written
against it. Deviate only with a reason.

---

## `config.json`

The one required file. It carries everything darktable knows about a model
before loading any ONNX graph.

```json
{
    "id": "mask-person-modnet",
    "name": "mask person modnet",
    "description": "MODNet for trimap-free portrait matting",
    "task": "person",
    "arch": "modnet",
    "backend": "onnx",
    "version": "0.1",
    "tiling": false,
    "model_card": { "author": "…", "license": "Apache-2.0" },
    "attributes": { "input_sizes": [512], "size_multiple": 32 }
}
```

### Fields

| Key | Type | Required | Read by darktable | Notes |
|---|---|---|---|---|
| `id` | string | yes | yes | Falls back to the directory name if absent, but always emit it. |
| `name` | string | yes | yes | Also surfaced as the model card's title. |
| `description` | string | yes | yes | |
| `task` | string | yes | yes | Determines which darktable feature can use the model, and which activation slot it competes for. |
| `version` | string | yes | yes | Compared against the remote catalogue to detect updates. Keep it a string. |
| `backend` | string | yes | no | Always `"onnx"` today. Required by `dtai validate`; darktable does not currently branch on it. |
| `arch` | string | no | no | Informational. |
| `tiling` | bool | no | no | Informational at the config level; tile size comes from `attributes.input_sizes`. |
| `spatial_dims` | `[string, string]` | no | yes | Symbolic names of the height and width dimensions in the ONNX graph. Defaults to `"height"` / `"width"`. **The SDK has no `model.yaml` field for this and never emits it** – see the gap note below. |
| `model_card` | object | no | yes | Provenance, rendered in the model info panel. Keys are looked up individually – see the [model card fields](model-yaml-spec.md#model-card-fields). |
| `attributes` | object | no | yes | Free-form runtime hints, read through typed accessors. See [attributes](model-yaml-spec.md#attributes). |
| `cpu_only` | list or object | no | – | Emitted when declared; reserved. |
| `coreml_format` | string or object | no | – | Emitted when declared; reserved. |

"Required" means `dtai validate` fails without it. Unknown keys are ignored by
both sides, which is the format's extension mechanism: adding a key is
backwards-compatible, older darktable builds skip it.

> **Known gap – `spatial_dims`.** darktable reads it; the SDK never writes it.
> Models exported with symbolic dimension names other than `height`/`width`
> need the key injected into `config.json` after `dtai convert` until
> `model.yaml` grows a field for it.

### Encoding

`generate_config_json` writes UTF-8 with `ensure_ascii=False`, 4-space indent,
and a trailing newline. Non-ASCII text in a model card (en dashes, accented
author names) is stored as real UTF-8 rather than escapes. Any JSON parser
handles the file; this is just what the reference output looks like.

---

## Installation semantics

Knowing how darktable installs a package explains most of the layout rules.

Given a `.dtmodel` file, darktable:

1. **Reads the model id** from the top-level directory of the first zip entry.
2. **Validates the id** as a safe path segment (rejects empty, `.`, `..`, and
   anything containing a path separator).
3. **Extracts into a staging directory** created with a unique suffix inside
   the models directory, so the extraction is on the same filesystem as its
   final destination.
4. **Verifies** that `staging/<model-id>/` exists – this is where a mismatched
   top-level directory is caught.
5. **Removes any existing install** at `<models-dir>/<model-id>/`, then
   **renames** the staged directory into place. The rename is atomic and
   intra-filesystem.
6. **Rescans** the models directory and, if no model is yet active for this
   model's task, activates it.

On any failure before step 5, staging is deleted and the previously installed
version is left untouched. A half-extracted archive can never replace a working
model – but note that step 5 does delete the old directory before the rename,
so the *previous* version is gone once the new one commits.

Installed layout on disk mirrors the archive:

```text
<darktable config dir>/ai_models/
└── upscale-bsrgan/
    ├── config.json
    └── model_x4.onnx
```

darktable also discovers models placed there by hand – anything with a readable
`config.json` is picked up on rescan as a local model. Unpacking a `.dtmodel`
into that directory yourself is equivalent to installing it.

---

## Distribution

Installing from a local file is the baseline path and needs nothing beyond the
archive itself: darktable's preferences has an *install from file* action that
takes a `.dtmodel`.

Automatic download is the other path, and it involves two index files. They live
in different places, which matters: one is committed to the repository, the
other is a release asset. `dtai versions` generates the second; the first is a
small file you maintain by hand. A scaffolded repo ships both a starter
`releases-index.json` and the CI that produces `versions.json` on a release tag.

### `releases-index.json`

**Committed at the repository root**, and read from the default branch:

```text
https://raw.githubusercontent.com/<owner>/<repo>/HEAD/releases-index.json
```

Maps a darktable version to the release tag whose assets it should use:

```json
{
  "schema": 1,
  "compatible_releases": {
    "5.5.0": "nightly-5.5.0",
    "5.6.0": "release-5.6.0"
  }
}
```

`schema` is the frozen contract version; darktable warns when it sees anything
other than `1`. A darktable version with no entry gets no downloads – this is
the mechanism that stops a new model format reaching an old build.

### `versions.json`

Published as an asset of each release, next to the `.dtmodel` files:

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

`version` drives update detection; `sha256` (note the mandatory `sha256:`
prefix) lets darktable verify a download and skip a rate-limited GitHub API
call per asset. The digest is over the whole `.dtmodel` file.

Assets are fetched from
`https://github.com/<owner>/<repo>/releases/download/<tag>/<model-id>.dtmodel`.

### The catalogue constraint

The list of *offerable* models – what appears in darktable's model manager
before anything is installed – comes from `ai_models.json` **bundled inside
darktable's own data directory**, not from your repository:

```json
{
  "version": 1,
  "models": [
    { "id": "denoise-nind", "name": "denoise nind", "task": "denoise",
      "min_version": "1.0", "default": true }
  ]
}
```

The `plugins/ai/repository` config key redirects *where assets are downloaded
from*, but the catalogue itself still comes from that bundled file. So a
third-party repository today reaches users through:

- **install-from-file** – ship `.dtmodel` files and let users install them
  directly; this works with no coordination at all, and installed models are
  fully first-class afterwards; or
- **repository redirect** – publish releases whose asset names match the ids
  darktable already lists, and have users point `plugins/ai/repository` at your
  repo. This substitutes your builds for the reference ones; it does not add new
  entries to the catalogue.

Getting a genuinely new model id into the built-in catalogue means a change to
darktable's `data/ai_models.json`, on darktable's release cycle.

---

## Versioning and compatibility

Three version numbers travel independently:

| Version | Where | Meaning |
|---|---|---|
| Model version | `config.json` → `version`, mirrored in `versions.json` | This model's own revision. Bump it whenever you republish a changed archive; that's what triggers an update prompt. |
| Index schema | `releases-index.json` → `schema` | Structure of the release index. Currently `1`. |
| Catalogue version | bundled `ai_models.json` → `version` | Structure of darktable's built-in model list. Currently `1`. |

The archive layout itself carries **no version field**. Extension is by adding
optional `config.json` keys, which both sides ignore when unrecognised. A change
that isn't expressible that way – renaming a required key, changing the
directory convention – is a breaking change to darktable's C loader and has to
be coordinated with a darktable release, gated through `compatible_releases` so
old builds never see the new assets.

Practical rules for producers:

- **Bump `version` on every republish.** A changed archive under an unchanged
  version leaves users on stale weights with no update signal.
- **Keep `version` a string.** `1.0` unquoted in YAML becomes a float and
  serialises differently; darktable compares strings.
- **Never recycle a model id** for a different model. The id is the install
  directory, the config key namespace, and the asset name.
- **Additive changes only** to `config.json` if you care about older darktable
  builds reading your packages.
