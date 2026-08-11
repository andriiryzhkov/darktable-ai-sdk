"""Helpers shared by the reusable CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import click

from dt_ai_sdk.config import ModelConfig, ModelConfigError, load_model_config
from dt_ai_sdk.discovery import discover_models, find_project_root


def get_root(ctx: click.Context) -> Path:
    """Resolve the repo root for a command, lazily.

    A downstream group that already knows its root keeps setting
    `ctx.obj["root"]` and this returns it untouched. Otherwise the root is
    discovered from the cwd on first use and cached – which is what lets
    the SDK's own `dtai` mount commands that need a repo alongside `init`,
    which must run outside one.
    """
    obj = ctx.ensure_object(dict)
    root = obj.get("root")
    if root is None:
        try:
            root = find_project_root()
        except FileNotFoundError as e:
            raise click.ClickException(str(e)) from e
        obj["root"] = root
    return root


def load_or_fail(root: Path, model_id: str) -> ModelConfig:
    """Load a single model config or exit with a clear error."""
    model_dir = root / "models" / model_id
    if not model_dir.is_dir():
        click.echo(f"Error: Model '{model_id}' not found in models/", err=True)
        sys.exit(1)
    try:
        return load_model_config(model_dir, root)
    except ModelConfigError as e:
        raise click.ClickException(str(e)) from e


def discover_or_fail(root: Path) -> list[ModelConfig]:
    """Discover every model, turning a bad model.yaml into a clean error.

    `dtai list` is the documented way to check a repo, so a malformed file
    must report which file – not a traceback from deep in the loader.
    """
    try:
        return discover_models(root)
    except ModelConfigError as e:
        raise click.ClickException(str(e)) from e


_default_sync_hook: Callable[[ModelConfig], None] | None = None


def set_sync_deps_hook(hook: Callable[[ModelConfig], None] | None) -> None:
    """Register a dep-sync hook for the whole process.

    Called once per model before convert and validate, so a repo whose
    models need conflicting dependency sets can install the right one.
    The SDK never assumes a package manager – name yours here:

        set_sync_deps_hook(lambda cfg: subprocess.run(
            ["uv", "sync", "--group", cfg.dep_group],
            cwd=str(cfg.root_dir), check=True,
        ))

    Importing the module that calls this is enough to arm it, which is
    what lets a repo extend the SDK's `dtai` group instead of replacing
    it. A group that builds its own context can still override per-run by
    setting `ctx.obj["sync_deps_hook"]`.
    """
    global _default_sync_hook
    _default_sync_hook = hook


def _sync_deps(ctx: click.Context, config: ModelConfig) -> None:
    """Invoke the dep-sync hook if one is registered."""
    hook = (ctx.obj.get("sync_deps_hook") if ctx.obj else None) or _default_sync_hook
    if hook is None:
        return
    hook(config)


def iter_selected_models(
    ctx: click.Context,
    model_id: str | None,
    callback: Callable[[ModelConfig], None],
    *,
    sync: bool = False,
) -> None:
    """Run callback for one named model or every non-skipped model.

    - `sync=True` invokes the dep-sync hook (if registered) per model.
    - Prints a header banner between models when iterating all of them.
    """
    root = get_root(ctx)

    if model_id:
        config = load_or_fail(root, model_id)
        if sync:
            _sync_deps(ctx, config)
        callback(config)
        return

    for config in discover_or_fail(root):
        if config.skip:
            click.echo(f"Skipping {config.id} (.skip)")
            continue
        click.echo(f"\n{'=' * 40}")
        click.echo(f"  {config.id}")
        click.echo(f"{'=' * 40}")
        if sync:
            _sync_deps(ctx, config)
        callback(config)
