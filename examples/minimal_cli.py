"""Embedding the SDK's commands in a CLI that isn't `dtai`.

**Most repositories don't need this.** `dtai` ships every command and finds
the repo from the cwd, and a repo adds its own commands by pointing
`[tool.dtai] extend` at a module – see `examples/minimal-repo/`.

This file covers the other case: mounting SDK commands inside a *different*
tool, under a name of your choosing, where you want explicit control over
the root and the dep-sync hook rather than the defaults. Every command here
is a plain Click object, so it composes anywhere.

Run as:
    python examples/minimal_cli.py list
    python examples/minimal_cli.py convert my-model-id

from inside a repo with `models/*/model.yaml` and a root `pyproject.toml`.
"""

from __future__ import annotations

import subprocess

import click

from dt_ai_sdk import find_project_root
from dt_ai_sdk.cli import (
    convert_cmd,
    list_cmd,
    package_cmd,
    run_cmd,
    setup_cmd,
    validate_cmd,
)


def _sync_via_uv(cfg) -> None:
    """Example dep-sync hook: uv sync --group <cfg.dep_group>.

    Swap for pip/poetry/pdm/none as your repo prefers. Return early for the
    'core' group so the base install isn't re-synced on every command.
    """
    if cfg.dep_group == "core":
        return
    click.echo(f"  Syncing dependency group: {cfg.dep_group}")
    subprocess.run(
        ["uv", "sync", "--group", cfg.dep_group],
        cwd=str(cfg.root_dir),
        check=True,
    )


@click.group()
@click.pass_context
def main(ctx):
    """Model-pipeline commands, hosted by a CLI of your own."""
    ctx.ensure_object(dict)
    # Both are optional. Without them the root is discovered from the cwd
    # and no hook runs – set them when you need to override that, e.g. to
    # drive a repo from outside it.
    ctx.obj["root"] = find_project_root()
    ctx.obj["sync_deps_hook"] = _sync_via_uv


# `init_cmd` is deliberately absent: scaffolding a new repo belongs to the
# SDK's own `dtai`, not to a CLI that operates on one existing repo.
for cmd in (setup_cmd, convert_cmd, validate_cmd,
            package_cmd, list_cmd, run_cmd):
    main.add_command(cmd)


if __name__ == "__main__":
    main()
