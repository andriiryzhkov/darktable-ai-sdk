"""Optional CLI extensions for this repository.

This file is not required to build the model – `dtai run identity` works
with only the SDK installed, because `dtai` ships every generic command and
finds this repo by walking up from the cwd.

It's here to demonstrate the extension path: register on the SDK's group
rather than shipping a competing `dtai` console script, which would collide
with the SDK's and let install order decide the winner.

Activated by the `[tool.dtai] extend` key in pyproject.toml, which `dtai`
reads on first command lookup.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from pathlib import Path

import click

from dt_ai_sdk.__main__ import main
from dt_ai_sdk.cli import get_root
from dt_ai_sdk.discovery import discover_models


# A repo whose models need conflicting dependency sets arms a hook here,
# and the SDK calls it once per model before convert and validate:
#
#   from dt_ai_sdk.cli import set_sync_deps_hook
#   set_sync_deps_hook(lambda cfg: subprocess.run(
#       ["uv", "sync", "--group", cfg.dep_group],
#       cwd=str(cfg.root_dir), check=True,
#   ))
#
# This example's single model needs nothing extra, so no hook.


def _project_name(root: Path) -> str:
    """Read the repo's name from pyproject.toml, falling back to the dir."""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            with open(pyproject, "rb") as f:
                name = tomllib.load(f).get("project", {}).get("name")
            if isinstance(name, str) and name:
                return name
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return root.name


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def _tally(label: str, counts: Counter) -> None:
    if not counts:
        return
    parts = ", ".join(f"{k} ({n})" for k, n in sorted(counts.items()))
    click.echo(f"  {label:<12} {parts}")


@main.command("info")
@click.pass_context
def info_cmd(ctx: click.Context) -> None:
    """Summarise this repository: its models, tasks, and built packages."""
    root = get_root(ctx)
    configs = discover_models(root)
    active = [c for c in configs if not c.skip]
    skipped = len(configs) - len(active)

    click.echo(f"\n{_project_name(root)}")
    click.echo(f"  {'root':<12} {root}")

    summary = f"{len(configs)}"
    if skipped:
        summary += f" ({skipped} skipped)"
    click.echo(f"  {'models':<12} {summary}")

    _tally("tasks", Counter(c.task for c in active))
    _tally("dep groups", Counter(c.dep_group for c in active))

    if not configs:
        click.echo("\nNo models yet – add one under models/<id>/model.yaml.")
        return

    click.echo("\nModels:")
    width = max(len(c.id) for c in configs)
    for cfg in configs:
        package = root / "output" / f"{cfg.id}.dtmodel"
        if cfg.skip:
            state = "skipped (.skip)"
        elif package.is_file():
            state = f"packaged, {_format_size(package.stat().st_size)}"
        elif (cfg.output_dir / "config.json").is_file():
            state = "converted, not packaged"
        else:
            state = "not built"
        click.echo(f"  {cfg.id:<{width}}  {cfg.task:<10} v{cfg.version:<6} {state}")

    click.echo()


if __name__ == "__main__":
    main()
