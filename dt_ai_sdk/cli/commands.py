"""Reusable Click commands: init, setup, convert, validate, package, list, run.

Each command is standalone and can be `add_command`ed onto any Click group.
The repo root is resolved lazily from the cwd (see `common.get_root`), so
these work with no wiring at all; a downstream group that already knows its
root can still pin it by setting `ctx.obj["root"]`, and may register an
optional `ctx.obj["sync_deps_hook"]` callable to install per-model
dependencies before convert/validate/demo.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from importlib import resources
from pathlib import Path

import click

from dt_ai_sdk import __version__ as SDK_VERSION
from dt_ai_sdk.cli.common import discover_or_fail, get_root, iter_selected_models
from dt_ai_sdk.config import ModelConfig
from dt_ai_sdk.convert import run_conversion
from dt_ai_sdk.discovery import discover_models
from dt_ai_sdk.download import download_checkpoints
from dt_ai_sdk.gitversion import describe_version, version_prefix
from dt_ai_sdk.package import package_model
from dt_ai_sdk.validate import run_validation


# Files in dt_ai_sdk/templates/repo/ are copied verbatim; occurrences of
# these tokens in file contents AND path components are replaced.
_TOKENS_IN_CONTENT = ("{{project_name}}", "{{module}}", "{{sdk_version}}")
_PKG_DIR_MARKER = "_pkg"          # renamed to <module> on copy
_GITIGNORE_SRC = "gitignore"      # renamed to .gitignore on copy
# Dot-prefixed directories are unreliable to ship inside a wheel, so the
# template tree stores CI as `github/` and it is renamed on copy.
_GITHUB_DIR_MARKER = "github"     # renamed to .github on copy


def _slug_to_module(name: str) -> str:
    """Turn a project name into a valid python module identifier."""
    module = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    if not module or module[0].isdigit():
        module = f"repo_{module}" if module else "repo"
    return module


def _substitute(text: str, project_name: str, module: str) -> str:
    return (text
            .replace("{{project_name}}", project_name)
            .replace("{{module}}", module)
            .replace("{{sdk_version}}", SDK_VERSION))


def _target_rel_path(rel_parts: tuple[str, ...], module: str) -> Path:
    """Map a template-tree relative path to its output location."""
    mapped = tuple(module if p == _PKG_DIR_MARKER else p for p in rel_parts)
    # only the top-level `github/` becomes `.github/`, so a nested
    # directory that happens to be called github is left alone
    if mapped and mapped[0] == _GITHUB_DIR_MARKER:
        mapped = (".github",) + mapped[1:]
    if mapped and mapped[-1] == _GITIGNORE_SRC:
        mapped = mapped[:-1] + (".gitignore",)
    return Path(*mapped)


def _iter_template_files(template_root):
    """Yield (relative_parts, Traversable) for every file in template_root.

    Skips the top-level `__init__.py` (there so `importlib.resources` can
    locate the dir) and any `__pycache__/` at any depth.
    """
    def walk(node, parts):
        for child in node.iterdir():
            if child.name == "__pycache__":
                continue
            if not parts and child.name == "__init__.py":
                continue
            child_parts = parts + (child.name,)
            if child.is_dir():
                yield from walk(child, child_parts)
            else:
                yield child_parts, child
    yield from walk(template_root, ())


@click.command("init")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path),
                default=".")
@click.option("--name", help="Project name (defaults to directory name)")
@click.option("--force", is_flag=True,
              help="Overwrite existing files in target")
def init_cmd(path: Path, name: str | None, force: bool) -> None:
    """Scaffold a new model repository at PATH (default: current dir)."""
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    project_name = name or path.name
    module = _slug_to_module(project_name)

    template_root = resources.files("dt_ai_sdk.templates")
    entries = [
        (_target_rel_path(rel, module), src)
        for rel, src in _iter_template_files(template_root)
    ]

    existing = [path / rel for rel, _ in entries if (path / rel).exists()]
    if existing and not force:
        click.echo("Error: refusing to overwrite existing files:", err=True)
        for f in existing:
            click.echo(f"  {f.relative_to(path)}", err=True)
        click.echo("Rerun with --force to replace them.", err=True)
        raise click.exceptions.Exit(1)

    for rel, src in entries:
        dest = path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        dest.write_text(_substitute(content, project_name, module),
                        encoding="utf-8")
        click.echo(f"  wrote {rel}")

    click.echo(f"\nInitialized {project_name} at {path}")
    click.echo("Next steps:")
    click.echo("  pip install -e .   # or: uv sync")
    click.echo("  dtai list")


@click.command("setup")
@click.argument("model_id", required=False)
@click.pass_context
def setup_cmd(ctx, model_id):
    """Download checkpoints and run repo setup commands."""
    root = get_root(ctx)

    def _setup(config: ModelConfig):
        if config.repo:
            repo_dir = config.repo_dir
            if repo_dir and not repo_dir.is_dir():
                click.echo(f"  Initializing submodule: {config.repo.submodule}")
                subprocess.run(
                    ["git", "submodule", "update", "--init", config.repo.submodule],
                    cwd=str(root), check=True,
                )

            if config.repo.setup and repo_dir and repo_dir.is_dir():
                click.echo(f"  Running repo setup: {config.repo.setup}")
                env = os.environ.copy()
                env["DTAI_ROOT"] = str(root)
                subprocess.run(
                    config.repo.setup, shell=True,
                    cwd=str(repo_dir), env=env, check=True,
                )

        if config.checkpoints:
            download_checkpoints(config.checkpoints, root)

    iter_selected_models(ctx, model_id, _setup)


@click.command("convert")
@click.argument("model_id", required=False)
@click.pass_context
def convert_cmd(ctx, model_id):
    """Convert model checkpoints to ONNX and emit config.json."""
    iter_selected_models(ctx, model_id, run_conversion, sync=True)


@click.command("validate")
@click.argument("model_id", required=False)
@click.pass_context
def validate_cmd(ctx, model_id):
    """Validate ONNX model output."""
    iter_selected_models(ctx, model_id, run_validation, sync=True)


@click.command("package")
@click.argument("model_id", required=False)
@click.pass_context
def package_cmd(ctx, model_id):
    """Package model as .dtmodel archive."""
    iter_selected_models(ctx, model_id, package_model)


@click.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON for CI")
@click.pass_context
def list_cmd(ctx, as_json):
    """List available models."""
    root = get_root(ctx)
    models = discover_or_fail(root)

    if as_json:
        matrix = [
            {"id": m.id, "dep_group": m.dep_group}
            for m in models if not m.skip
        ]
        click.echo(json.dumps(matrix))
    else:
        for config in models:
            status = " (skipped)" if config.skip else ""
            click.echo(f"  {config.id:<35} {config.task:<15} {config.description}{status}")


@click.command("git-version")
@click.option("--prefix", is_flag=True,
              help="Print only the X.Y.Z part (empty if no release-* tag).")
@click.pass_context
def git_version_cmd(ctx, prefix):
    """Print the repo's version, derived from its `release-*` git tags.

    Named `git-version` rather than `version` to keep it distinct from
    `dtai --version`, which reports the SDK's own version.
    """
    root = get_root(ctx)
    if prefix:
        click.echo(version_prefix(root) or "")
    else:
        click.echo(describe_version(root))


@click.command("versions")
@click.option(
    "--artifacts-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory holding built .dtmodel files; when given, a sha256 "
         "digest for each model is included.",
)
@click.pass_context
def versions_cmd(ctx, artifacts_dir):
    """Write output/versions.json for a release.

    darktable reads this next to the .dtmodel assets for three things: to
    decide whether an update is available, to verify a download without
    spending a rate-limited API call per asset, and to list what a release
    offers. That last use is why entries carry display metadata – a model
    published after a given darktable build is absent from its bundled
    catalogue, so this file is the only place its name and task can come
    from. See docs/dtmodel-format.md.

    `sha256` and `size` need the built archive, so they appear only with
    --artifacts-dir.
    """
    import hashlib

    root = get_root(ctx)
    models = sorted((m for m in discover_or_fail(root) if not m.skip),
                    key=lambda m: m.id)

    entries: dict[str, dict] = {}
    for m in models:
        entry: dict = {"version": m.version}
        # Enough to choose a model before downloading it, and no more: the
        # full model card stays in the package's config.json, since this
        # file is fetched on every update check.
        if m.name:
            entry["name"] = m.name
        if m.description:
            entry["description"] = m.description
        if m.task:
            entry["task"] = m.task
        license_ = m.model_card.get("license")
        if license_:
            entry["license"] = license_
        entries[m.id] = entry

    if artifacts_dir is not None:
        for m in models:
            # accept both the CI layout from actions/download-artifact and
            # the flat output/ layout that `dtai package` produces locally
            nested = artifacts_dir / m.id / f"{m.id}.dtmodel"
            flat = artifacts_dir / f"{m.id}.dtmodel"
            path = nested if nested.is_file() else flat
            if not path.is_file():
                click.echo(f"Warning: artifact missing for {m.id}: "
                           f"{nested} or {flat}", err=True)
                continue
            digest = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            # the "sha256:" prefix is required – darktable ignores the
            # value without it
            entries[m.id]["sha256"] = f"sha256:{digest.hexdigest()}"
            # download size, so an installer can say what it is about to
            # fetch rather than starting a large transfer unannounced
            entries[m.id]["size"] = path.stat().st_size

    # schema is frozen at 1; consumers should warn on anything else rather
    # than guess, as darktable already does for releases-index.json
    data = {"schema": 1, "models": entries}

    output_path = root / "output" / "versions.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    click.echo(f"Generated {output_path}")


@click.command("run")
@click.argument("model_id", required=False)
@click.pass_context
def run_cmd(ctx, model_id):
    """Run full pipeline: setup -> convert -> validate -> package."""

    def _run_pipeline(config: ModelConfig):
        click.echo("\n=== Setup ===")
        ctx.invoke(setup_cmd, model_id=config.id)

        click.echo("\n=== Convert ===")
        run_conversion(config)

        click.echo("\n=== Validate ===")
        run_validation(config)

        click.echo("\n=== Package ===")
        package_model(config)

    iter_selected_models(ctx, model_id, _run_pipeline, sync=True)
