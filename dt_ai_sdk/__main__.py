"""The `dtai` command.

Ships the whole command set. The repo root is discovered by walking up from
the current directory, so `dtai` works inside any model repository with no
per-repo wiring – installing the SDK is enough:

    pip install darktable-ai-sdk
    cd my-models && dtai run

`init` is the exception: it runs outside a repo, which is why the root is
resolved lazily by the commands that need it rather than up front.

A repository that adds its own commands or a dependency-sync hook does not
need its own entry point either. It points at an extension module from its
pyproject.toml:

    [tool.dtai]
    extend = "my_models.cli"

which this group imports on first command lookup. That module registers
whatever it likes on the shared group:

    from dt_ai_sdk.__main__ import main

    @main.command("demo")
    def demo_cmd(): ...

Keeping `dtai` owned by exactly one package is deliberate: two packages
installing a console script of the same name collide, and the winner is
decided by install order.

Invoke as:
    dtai run                      # via project.scripts
    python -m dt_ai_sdk run       # or the module form
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import click

from dt_ai_sdk import __version__
from dt_ai_sdk.cli import (
    convert_cmd,
    git_version_cmd,
    init_cmd,
    list_cmd,
    package_cmd,
    run_cmd,
    setup_cmd,
    validate_cmd,
    versions_cmd,
)
from dt_ai_sdk.discovery import find_project_root


def _read_extension_target(root: Path) -> str | None:
    """Read `[tool.dtai] extend` from the repo's pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    target = data.get("tool", {}).get("dtai", {}).get("extend")
    return target if isinstance(target, str) and target else None


class _ExtensibleGroup(click.Group):
    """Group that imports the current repo's CLI extension on demand.

    Loading is deferred to the first command lookup rather than done at
    import time, so `dtai init` still works outside a repository – there
    is no root to find there, and nothing to load.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._extension_loaded = False

    def _load_extension(self) -> None:
        if self._extension_loaded:
            return
        self._extension_loaded = True  # set first: one attempt, success or not

        try:
            root = find_project_root()
        except FileNotFoundError:
            return

        target = _read_extension_target(root)
        if not target:
            return

        try:
            importlib.import_module(target)
        except ImportError as e:
            # Loud, not silent: a declared extension that won't import is a
            # broken repo, and silently missing commands is worse to debug.
            raise click.ClickException(
                f"could not import CLI extension '{target}' declared in "
                f"{root / 'pyproject.toml'}: {e}"
            ) from e

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_extension()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        self._load_extension()
        return super().get_command(ctx, name)


@click.group(cls=_ExtensibleGroup)
@click.version_option(__version__, prog_name="dtai")
@click.pass_context
def main(ctx: click.Context) -> None:
    """dtai: build and package models for darktable."""
    # Only the object store is set up here. The root is deliberately not
    # resolved yet – `init` runs outside a repo, and resolving eagerly
    # would make it fail there.
    ctx.ensure_object(dict)


for _cmd in (init_cmd, setup_cmd, convert_cmd, validate_cmd,
             package_cmd, list_cmd, run_cmd, versions_cmd,
             git_version_cmd):
    main.add_command(_cmd)


if __name__ == "__main__":
    main()
