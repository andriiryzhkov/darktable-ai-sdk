"""Reusable Click commands for building a `dtai`-style CLI.

Most repositories need nothing from this module: the SDK's own `dtai`
already ships every command here and finds the repo root on its own.

Reach for it when a repository adds commands or a dependency-sync hook.
The easy way is to extend the SDK's group, so your `dtai` is a superset of
the stock one:

    from dt_ai_sdk.__main__ import main

    @main.command("demo")
    def demo_cmd(): ...

Building a group from scratch is also supported – mount whichever commands
you want and, if the root isn't discoverable from the cwd, pin it:

    import click
    from dt_ai_sdk import find_project_root
    from dt_ai_sdk.cli import convert_cmd, list_cmd, package_cmd

    @click.group()
    @click.pass_context
    def main(ctx):
        ctx.ensure_object(dict)
        ctx.obj["root"] = find_project_root()   # optional; lazy by default

    for cmd in (convert_cmd, list_cmd, package_cmd):
        main.add_command(cmd)
"""

from __future__ import annotations

from dt_ai_sdk.cli.common import (
    discover_or_fail,
    get_root,
    iter_selected_models,
    load_or_fail,
    set_sync_deps_hook,
)
from dt_ai_sdk.cli.commands import (
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

__all__ = [
    "convert_cmd",
    "discover_or_fail",
    "git_version_cmd",
    "get_root",
    "init_cmd",
    "iter_selected_models",
    "list_cmd",
    "load_or_fail",
    "package_cmd",
    "run_cmd",
    "set_sync_deps_hook",
    "setup_cmd",
    "validate_cmd",
    "versions_cmd",
]
