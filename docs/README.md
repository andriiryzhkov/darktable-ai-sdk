# Darktable AI SDK documentation

These docs are for anyone building a **model repository** – a repo that
declares models in YAML and produces `.dtmodel` packages darktable can install.

The SDK's job is compatibility: it builds packages to the format darktable
reads and validates them before you ship. Distribution is a separate matter
with real constraints – read
[the three things worth knowing](#three-things-worth-knowing-up-front) before
planning around it.

If you are working on the SDK itself instead, its test setup and PyPI release
process live in the top-level [README](../README.md#releasing).

---

## Start here

```bash
uvx --from darktable-ai-sdk dtai init ./my-models
cd my-models && dtai list
```

Then read [**building-a-repo.md**](building-a-repo.md), which walks the whole
path: scaffold, describe a model, write its conversion script, build, and ship.

For something you can run immediately, [`examples/minimal-repo/`](../examples/minimal-repo/)
is a complete repository that builds a real `.dtmodel` in about a second, with
no weights to download. It's the quickest way to confirm a toolchain works
before pointing it at a real model.

---

## The four documents

| Document | Answers |
|---|---|
| [building-a-repo.md](building-a-repo.md) | How do I go from a trained model to an installable package? |
| [model-yaml-spec.md](model-yaml-spec.md) | What can I put in `model.yaml`, and what does each field do? |
| [ci-and-releasing.md](ci-and-releasing.md) | How do the scaffolded GitHub Actions work, and how do I cut a release? |
| [dtmodel-format.md](dtmodel-format.md) | What's inside a `.dtmodel`, and how does darktable install and update it? |

### building-a-repo.md

The guided path, in seven steps. Also covers the things that trip people up
early: which `dtai` you get in which environment, how to handle models whose
dependencies can't coexist, and how to add repo-specific commands.

### model-yaml-spec.md

The reference for the input contract. Every field, its default, and whether it
reaches the shipped package – including the ones that look meaningful but
aren't read, and the `.skip` marker that isn't a field at all.

### ci-and-releasing.md

The three workflows `dtai init` scaffolds, how one CI job per model falls out
of `dtai list --json-output`, the two index files darktable reads
(`versions.json` and `releases-index.json`), and what a fresh repo needs before
its first green run.

### dtmodel-format.md

The output contract: archive layout, every `config.json` key and whether
darktable reads it, the install sequence, and how versioning and compatibility
work. Read this if you're writing tooling against the format rather than just
using it.

---

## Finding an answer quickly

| If you're wondering | Look at |
|---|---|
| Which `task` values darktable actually dispatches on | [model-yaml-spec.md](model-yaml-spec.md#required-fields) |
| Why my conversion script's arguments aren't substituting | [Template variables](model-yaml-spec.md#template-variables) |
| What `dtai validate` expects to find | [Output layout by type](model-yaml-spec.md#output-layout-by-type) |
| How to declare provenance and licensing | [Model card fields](model-yaml-spec.md#model-card-fields) |
| Why `dtai validate` can't find onnxruntime | [building-a-repo.md](building-a-repo.md#1-scaffold) |
| How models with conflicting dependencies build | [dep_group and the sync hook](building-a-repo.md#5-handle-differing-dependencies) |
| Why my CI fails on an unknown dependency group | [Before your first green run](ci-and-releasing.md#before-your-first-green-run) |
| Why users aren't offered my update | [What to bump first](ci-and-releasing.md#what-to-bump-first) |
| What has to be true of the archive | [Archive layout](dtmodel-format.md#archive-layout) |
| Whether darktable reads a given `config.json` key | [Fields](dtmodel-format.md#fields) |
| How a third-party repo reaches users at all | [The catalogue constraint](dtmodel-format.md#the-catalogue-constraint) |
| Whether it's safe to run `dtai` in someone else's repo | [Running dtai on a repository you didn't write](building-a-repo.md#running-dtai-on-a-repository-you-didnt-write) |

---

## Three things worth knowing up front

All are documented in full below, but they shape what's worth planning for.

**The catalogue of downloadable models is bundled inside darktable**, not read
from your repository. Pointing darktable's `plugins/ai/repository` setting at
your repo changes where assets are *fetched from*, but not which model ids are
offered. So install-from-file is the path to plan around for a genuinely new
model; getting a new id into the built-in catalogue happens on darktable's
release cycle. See [the catalogue constraint](dtmodel-format.md#the-catalogue-constraint).

**An unchanged `version` means users keep the old weights**, no matter how
different the archive is – darktable compares version strings, not content.
Bump `version:` in `model.yaml` on every republish. See
[what to bump first](ci-and-releasing.md#what-to-bump-first).

**A model repository is code, and `dtai` executes it.** Conversion scripts,
`repo.setup` commands and a declared CLI extension all run as you – the
extension before *any* command, so even `dtai list` is not read-only. Read a
repo you didn't write before running `dtai` in it. See
[running dtai on a repository you didn't write](building-a-repo.md#running-dtai-on-a-repository-you-didnt-write).
Installing a built `.dtmodel` is far narrower: it is ONNX plus JSON, and
nothing in it executes.

---

## Elsewhere

- [`examples/minimal-repo/`](../examples/minimal-repo/) – a working repo, no
  downloads needed
- [`examples/minimal_cli.py`](../examples/minimal_cli.py) – embedding the SDK's
  commands in a CLI that isn't `dtai`
- [darktable-ai](https://github.com/darktable-org/darktable-ai) – the reference
  repository, with a dozen real models
